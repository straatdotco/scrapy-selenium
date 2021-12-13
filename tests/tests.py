import unittest
import scrapy
from scrapy_selenium.http import SeleniumRequest
from shutil import which
from scrapy_selenium.middlewares import SeleniumMiddleware
from scrapy.crawler import Crawler
from scrapy.crawler import CrawlerProcess


class TestSpider(scrapy.Spider):
    name = 'test_spider'
    allowed_domains = ['lbilimited.com', 'www.lbilimited.com']
    #start_urls = ['https://classic.com']
    custom_settings = {
        #'SELENIUM_DRIVER_NAME': 'uc',
        #'SELENIUM_DRIVER_EXECUTABLE_PATH': which('geckodriver'),
        'SELENIUM_DRIVER_ARGUMENTS': ['--headless'],
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy_selenium.SeleniumMiddleware': 800
        },
        'HTTPERROR_ALLOW_ALL': True,
        # 'COMPRESSION_ENABLED': False
    }

    def start_requests(self):
        #yield SeleniumRequest(url='https://github.com', screenshot=True, infinite_scroll=20000)
        #yield SeleniumRequest(url='https://lbilimited.com/offerings/1930-rolls-royce-phantom-1/', screenshot=True, infinite_scroll=20000)
        yield SeleniumRequest(url='https://lbilimited.com/current-offerings/', screenshot=True, infinite_scroll=20000)


    def parse(self, response):
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