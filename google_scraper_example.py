import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import pandas as pd
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Logging beállítása
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


def google_search(query, num_results=5, pause=2.0):
    """
    Lekérdezi a Google-t és visszaadja az első num_results találat címét és linkjét.
    """
    try:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        )
        headers = {"User-Agent": user_agent}
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for g in soup.select('div.g')[:num_results]:
            link_tag = g.select_one('a')
            title_tag = g.select_one('h3')
            if link_tag and title_tag:
                results.append({'title': title_tag.get_text(), 'link': link_tag['href']})
        time.sleep(pause)
        return results
    except requests.RequestException as e:
        logging.warning(f"Google keresés sikertelen: {e}")
        return []


def fetch_openfoodfacts(ean):
    """
    Fallback: OpenFoodFacts API lekérdezése JSON formátumban.
    """
    off_url = f"https://world.openfoodfacts.org/api/v0/product/{ean}.json"
    try:
        resp = requests.get(off_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('status') == 1:
            prod = data['product']
            return {
                'title': prod.get('product_name', ''),
                'description': prod.get('generic_name', ''),
                'ingredients': prod.get('ingredients_text', ''),
                'effects': prod.get('nutriments', {}).get('nutrition_grade_fr', ''),
                'packaging': prod.get('packaging', ''),
                'link': off_url
            }
    except Exception as e:
        logging.warning(f"OpenFoodFacts API hiba: {e}")
    return None


def scrape_product_info(url):
    """
    Scraping oldalról: összetevők, hatások, kiszerelés, meta leírás.
    """
    try:
        headers = {"User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        )}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        result = {'ingredients': '', 'effects': '', 'packaging': '', 'description': ''}

        # Összetevők
        ing = soup.find(text=lambda t: 'Összetevők' in t)
        if ing:
            result['ingredients'] = ing.parent.get_text(separator=' ', strip=True)

        # Hatások vagy előnyök
        effect = soup.find(text=lambda t: 'Hatás' in t or 'Előny' in t)
        if effect:
            result['effects'] = effect.parent.get_text(separator=' ', strip=True)

        # Kiszerelés
        pack = soup.find(text=lambda t: any(unit in t for unit in ['g', 'ml']))
        if pack:
            result['packaging'] = pack.parent.get_text(separator=' ', strip=True)

        # Meta leírás
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta and meta.get('content'):
            result['description'] = meta['content'].strip()
        else:
            # Termékleírás blokk keresése
            desc_div = soup.find(
                lambda tag: (
                    tag.name in ['div', 'p']
                    and tag.get('class')
                    and any(
                        'description' in c.lower()
                        for c in tag.get('class')
                    )
                )
            )
            if desc_div:
                result['description'] = (
                    desc_div.get_text(
                        separator=' ',
                        strip=True
                    )
                )
        return result
    except requests.RequestException as e:
        logging.warning(f"Scraping sikertelen {url}: {e}")
        return {'ingredients': '', 'effects': '', 'packaging': '', 'description': ''}


def fetch_product_data(ean):
    """
    Összefogja Google keresést, scrapinget, és ha kell, OpenFoodFacts fallback-et.
    """
    results = google_search(ean, num_results=3)
    if results:
        first = results[0]
        scraped = scrape_product_info(first['link'])
        data = {'EAN': ean, 'title': first['title'], 'link': first['link'], **scraped}
        if not data['description'] or not data['ingredients']:
            off = fetch_openfoodfacts(ean)
            if off:
                for key in ['title', 'description', 'ingredients', 'effects', 'packaging', 'link']:
                    if not data.get(key) and off.get(key):
                        data[key] = off[key]
        return data
    off = fetch_openfoodfacts(ean)
    if off:
        return {'EAN': ean, **off}
    logging.error(f"Adatgyűjtés sikertelen EAN: {ean}")
    return {'EAN': ean, 'title': '', 'link': '', 'ingredients': '', 'effects': '', 'packaging': '', 'description': ''}


def main():
    df = pd.read_csv('products.csv', dtype=str)
    if 'EAN' not in df.columns:
        raise ValueError("A CSV-nek tartalmaznia kell az 'EAN' oszlopot.")

    records = []
    for idx, row in df.iterrows():
        ean = row['EAN']
        logging.info(f"Feldolgozás: {ean} ({idx+1}/{len(df)})")
        records.append(fetch_product_data(ean))

    raw_df = pd.DataFrame(records)
    raw_df.to_csv('product_data_raw.csv', index=False)
    logging.info("Nyers adat elmentve: product_data_raw.csv")

    env = Environment(loader=FileSystemLoader('.'), autoescape=select_autoescape(['html']))
    template = env.get_template('description_template.html')

    descriptions = []
    for _, prod in raw_df.iterrows():
        html = template.render(
            product_name=prod['title'],
            description=prod['description'],
            ingredients=prod['ingredients'],
            effects=prod['effects'],
            packaging=prod['packaging']
        )
        descriptions.append(html)

    raw_df['DescriptionHTML'] = descriptions
    raw_df.to_csv('product_data_with_descriptions.csv', index=False)
    logging.info("Leírások elmentve: product_data_with_descriptions.csv")


if __name__ == '__main__':
    main()

# Készítsd el a 'description_template.html'-t a korábbi instrukciók szerint.
