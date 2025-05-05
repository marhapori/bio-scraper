import os
import sys

# A projekt gyökere (a tests mappa egy szinttel feljebb)
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
)

from google_scraper_example import fetch_product_data


def test_fetch_product_data_opensuccess(mocker):
    mocker.patch(
        'google_scraper_example.google_search',
        return_value=[{'title': 'Termék', 'link': 'http://example.com'}],
    )
    mocker.patch(
        'google_scraper_example.scrape_product_info',
        return_value={
            'ingredients': 'Összetétel',
            'effects': 'Hatás',
            'packaging': '50g',
            'description': 'Leírás',
        },
    )

    data = fetch_product_data('1234567890123')

    assert data['title'] == 'Termék'
    assert 'Összetétel' in data['ingredients']
