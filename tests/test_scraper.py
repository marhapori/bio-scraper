# flake8: noqa: E402
import os
import sys

# Projekt gyökerének felvétele a modulkereső útvonalra
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..')),
)

from google_scraper_example import (
    fetch_product_data,
    search_termeszetes,
    scrape_product_info,
)

def test_fetch_product_data_opensuccess(mocker):
    # Mockoljuk a belső keresőt: adjon vissza címet és linket
    mocker.patch(
        'google_scraper_example.search_termeszetes',
        return_value=('Termék', 'http://example.com'),
    )
    # Mockoljuk a scrapinget: adja vissza a mezőket
    mocker.patch(
        'google_scraper_example.scrape_product_info',
        return_value={
            'ingredients': 'Összetétel',
            'effects': 'Hatás',
            'packaging': '50g',
            'description': 'Leírás',
        },
    )

    # Most már két paraméterrel hívjuk: EAN és terméknév
    data = fetch_product_data('1234567890123', 'TestProduct')

    assert data['title'] == 'Termék'
    assert 'Összetétel' in data['ingredients']
