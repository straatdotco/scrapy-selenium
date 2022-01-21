import unittest
import scrapy
from scrapy_selenium.http import SeleniumRequest
from shutil import which
from scrapy_selenium.middlewares import SeleniumMiddleware
from scrapy.crawler import Crawler
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor


class TestSpider(scrapy.Spider):
    name = 'test_spider'
    allowed_domains = ['lbilimited.com', 'www.lbilimited.com', 'luxeautomotivesales.com']
    #start_urls = ['https://classic.com']
    custom_settings = {
        #'SELENIUM_DRIVER_NAME': 'uc',
        #'SELENIUM_DRIVER_EXECUTABLE_PATH': which('geckodriver'),
        'SELENIUM_DRIVER_ARGUMENTS': ['--headless'],
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy_selenium.SeleniumMiddleware': 800
        },
        'HTTPERROR_ALLOW_ALL': True,
        'SELENIUM_PROXY': '3.218.234.61:3128',
        'RETRY_ENABLED': False,
        'SELENIUM_TIMEOUT': 60,
        # 'COMPRESSION_ENABLED': False
    }

    def start_requests(self):
        #yield SeleniumRequest(url='https://github.com', screenshot=True, infinite_scroll=20000)
        #yield SeleniumRequest(url='https://lbilimited.com/offerings/1930-rolls-royce-phantom-1/', screenshot=True, infinite_scroll=20000)
        #yield SeleniumRequest(url='https://lbilimited.com/current-offerings/', screenshot=True, infinite_scroll=20000)
        #yield SeleniumRequest(url='https://luxeautomotivesales.com/for-sale/', screenshot=True, infinite_scroll=20000)
        #yield SeleniumRequest(url='https://www.ryanfriedmanmotorcars.com/sold-inventory/', screenshot=False, wait_time=30, infinite_scroll=20000)
        #yield SeleniumRequest(url='http://rmcmiami.com/inventory/1982-911-turbo-dp-1-935-ruf-btr-engine-speed-record-car-for-car-driver-magazine/', screenshot=False, wait_time=5, infinite_scroll=False)
        # yield SeleniumRequest(
        #     url='https://api.ipify.org',
        #     screenshot=False, wait_time=5, infinite_scroll=False, proxy=True
        # )
        # yield SeleniumRequest(
        #     url='https://uploadbeta.com/api/user-agent/',
        #     screenshot=False, wait_time=5, infinite_scroll=False, proxy=True
        # )

        yield SeleniumRequest(
            url='http://rmcmiami.com/inventory/1986-porsche-911-gemballa-slant-nose-gemballa-wide-body-pionner-sound-system-show-car-1-of-handful-ever-built/',
            screenshot=True,
            wait_time=1,
            infinite_scroll=True,
            proxy=True,
            timeout=300
        )


    def parse(self, response):
        item_extractor = LinkExtractor(allow='\/\d{4}-')
        item_links = item_extractor.extract_links(response)

        breakpoint()
        return response
        #pass


class TestMiddleware(unittest.TestCase):

    def test_download(self):
        process = CrawlerProcess()
        process.crawl(TestSpider)
        process.start()


if __name__ == '__main__':
    unittest.main()