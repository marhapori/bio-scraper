import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import pandas as pd
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape


# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)


def google_search(query, num_results=5, pause=2.0):
    """
    Queries Google and returns the first num_results results (title and link).
    """
    try:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        )
        headers = {"User-Agent": user_agent}
        url = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(query)
        )
        resp = requests.get(
            url,
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for g in soup.select('div.g')[:num_results]:
            link_tag = g.select_one('a')
            title_tag = g.select_one('h3')
            if link_tag and title_tag:
                results.append({
                    'title': title_tag.get_text(),
                    'link': link_tag['href']
                })
        time.sleep(pause)
        return results

    except requests.RequestException as e:
        logging.warning(
            f"Google search failed for query '{query}': {e}"
        )
        return []


def scrape_product_info(url):
    """
    Scrapes a product page for ingredients, effects, packaging, and description.
    """
    try:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        )
        headers = {"User-Agent": user_agent}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        result = {
            'ingredients': '',
            'effects': '',
            'packaging': '',
            'description': ''
        }
        ing = soup.find(text=lambda t: 'Összetevők' in t)
        if ing:
            result['ingredients'] = ing.parent.get_text(
                separator=' ', strip=True
            )
        eff = soup.find(text=lambda t: 'Hatás' in t or 'Előny' in t)
        if eff:
            result['effects'] = eff.parent.get_text(
                separator=' ', strip=True
            )
        pkg = soup.find(text=lambda t: any(
            u in t for u in ['g', 'ml']
        ))
        if pkg:
            result['packaging'] = pkg.parent.get_text(
                separator=' ', strip=True
            )
        meta = soup.find(
            'meta', attrs={'name': 'description'}
        )
        if meta and meta.get('content'):
            result['description'] = meta['content'].strip()
        else:
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
                result['description'] = desc_div.get_text(
                    separator=' ', strip=True
                )
        return result

    except requests.RequestException as e:
        logging.warning(
            f"Scraping failed for URL {url}: {e}"
        )
        return {
            'ingredients': '',
            'effects': '',
            'packaging': '',
            'description': ''
        }


def fetch_bionaturorganikus(ean):
    """
    Fallback: Search bionaturorganikus.hu for the product by EAN.
    """
    query = f"site:bionaturorganikus.hu {ean}"
    results = google_search(query, num_results=3)
    if results:
        first = results[0]
        scraped = scrape_product_info(first['link'])
        return {
            'title': first['title'],
            'description': scraped.get('description', ''),
            'ingredients': scraped.get('ingredients', ''),
            'effects': scraped.get('effects', ''),
            'packaging': scraped.get('packaging', ''),
            'link': first['link']
        }
    return None


def fetch_product_data(ean):
    """
    Main orchestration: first search termeszetes.com/en, then fallback to bionaturorganikus.hu.
    """
    primary_query = f"site:termeszetes.com/en {ean}"
    results = google_search(primary_query, num_results=3)
    if results:
        first = results[0]
        scraped = scrape_product_info(first['link'])
        data = {
            'EAN': ean,
            'title': first['title'],
            'link': first['link'],
            **scraped
        }
        if not data['description'] or not data['ingredients']:
            fallback = fetch_bionaturorganikus(ean)
            if fallback:
                for key in [
                    'title', 'description', 'ingredients',
                    'effects', 'packaging', 'link'
                ]:
                    if not data.get(key) and fallback.get(key):
                        data[key] = fallback[key]
        return data
    fallback = fetch_bionaturorganikus(ean)
    if fallback:
        return {'EAN': ean, **fallback}
    logging.error(
        f"Data collection failed for EAN: {ean}"
    )
    return {
        'EAN': ean, 'title': '', 'link': '',
        'ingredients': '', 'effects': '',
        'packaging': '', 'description': ''
    }


def main():
    df = pd.read_csv('products.csv', dtype=str)
    if 'EAN' not in df.columns:
        raise ValueError("CSV must contain an 'EAN' column.")
    records = []
    for idx, row in df.iterrows():
        ean = row['EAN']
        logging.info(
            f"Processing {ean} ({idx+1}/{len(df)})"
        )
        records.append(fetch_product_data(ean))
    raw_df = pd.DataFrame(records)
    raw_df.to_csv(
        'product_data_raw.csv', index=False
    )
    logging.info("Raw data saved to product_data_raw.csv")
    env = Environment(
        loader=FileSystemLoader('.'),
        autoescape=select_autoescape(['html'])
    )
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
    raw_df.to_csv(
        'product_data_with_descriptions.csv', index=False
    )
    logging.info("Descriptions saved to product_data_with_descriptions.csv")


if __name__ == '__main__':
    main()
