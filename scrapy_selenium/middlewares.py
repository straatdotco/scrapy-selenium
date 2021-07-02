"""This module contains the ``SeleniumMiddleware`` scrapy middleware"""

from importlib import import_module
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from selenium.webdriver.support.ui import WebDriverWait
import seleniumwire.undetected_chromedriver.v2 as uc
import logging
from selenium.webdriver.remote.remote_connection import LOGGER as seleniumLogger
from urllib3.connectionpool import log as urllibLogger
from .http import SeleniumRequest
from urllib.parse import urlparse


class SeleniumMiddleware:
    """Scrapy middleware handling the requests using selenium"""

    def __init__(self, driver_name, driver_executable_path,
                    browser_executable_path, command_executor, driver_arguments):
        """Initialize the selenium webdriver

        Parameters
        ----------
        driver_name: str
            The selenium ``WebDriver`` to use
        driver_executable_path: str
            The path of the executable binary of the driver
        driver_arguments: list
            A list of arguments to initialize the driver
        browser_executable_path: str
            The path of the executable binary of the browser
        command_executor: str
            Selenium remote server endpoint
        """
        self.driver_name = driver_name
        self.driver_executable_path = driver_executable_path
        self.driver_arguments = driver_arguments
        self.browser_executable_path = browser_executable_path
        self.command_executor =  command_executor
        self.driver = None

    def load_driver(self):
        """
        Initialize the selenium UC webdriver via selenium wire
        """
        # uses https://github.com/ultrafunkamsterdam/undetected-chromedriver to bypass blocking
        options = uc.ChromeOptions()
        try:
            for argument in self.driver_arguments:
                options.add_argument(argument)
        except:
            pass
        #options.add_argument('--enable_cdp_event=True')
        #options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        # raise the logging level for selenium-wire
        selenium_logger = logging.getLogger('seleniumwire')
        selenium_logger.setLevel(logging.ERROR)
        hpack_logger = logging.getLogger('hpack')
        hpack_logger.setLevel(logging.ERROR)
        seleniumLogger.setLevel(logging.WARNING)
        urllibLogger.setLevel(logging.WARNING)
        self.driver = uc.Chrome(options=options)

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings"""
        driver_name = crawler.settings.get('SELENIUM_DRIVER_NAME')
        driver_executable_path = crawler.settings.get('SELENIUM_DRIVER_EXECUTABLE_PATH')
        browser_executable_path = crawler.settings.get('SELENIUM_BROWSER_EXECUTABLE_PATH')
        command_executor = crawler.settings.get('SELENIUM_COMMAND_EXECUTOR')
        driver_arguments = crawler.settings.get('SELENIUM_DRIVER_ARGUMENTS')

        '''
        if driver_name is None:
            raise NotConfigured('SELENIUM_DRIVER_NAME must be set')

        if driver_executable_path is None and command_executor is None:
            raise NotConfigured('Either SELENIUM_DRIVER_EXECUTABLE_PATH '
                                'or SELENIUM_COMMAND_EXECUTOR must be set')
        '''

        middleware = cls(
            driver_name=driver_name,
            driver_executable_path=driver_executable_path,
            browser_executable_path=browser_executable_path,
            command_executor=command_executor,
            driver_arguments=driver_arguments
        )

        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)

        return middleware

    def process_request(self, request, spider):
        """Process a request using the selenium driver if applicable"""

        def compare_urls(url_1, url_2):
            """
            Compares 2 urls to see if they are the same based on scheme, hostname, path and query, ignoring port
            Parameters
            ----------
            url_1 - string
            url_2 - string

            Returns
            -------
            bool - False if they don't match, True if they do
            """
            url_1 = urlparse(url_1)
            url_2 = urlparse(url_2)
            if url_2.scheme != url_1.scheme:
                return False
            if url_2.hostname != url_1.hostname:
                return False
            if url_2.path != url_1.path:
                return False
            if url_2.query != url_1.query:
                return False
            return True

        def clean_url(url):
            """
            Cleans the url
            eg: removes things like port which don't appear in response urls after redirect
            Parameters
            ----------
            url - the url to clean

            Returns
            -------
            cleaned_url - string - cleaned url
            """
            parsed_url = urlparse(url)
            cleaned_url = f'{parsed_url.scheme}://{parsed_url.hostname}{parsed_url.path}'
            if len(parsed_url.query) > 0:
                cleaned_url += f'?{parsed_url.query}'
            return cleaned_url

        if not isinstance(request, SeleniumRequest):
            return None

        # open the driver
        self.load_driver()

        self.driver.get(request.url)

        for cookie_name, cookie_value in request.cookies.items():
            self.driver.add_cookie(
                {
                    'name': cookie_name,
                    'value': cookie_value
                }
            )

        if request.wait_until:
            WebDriverWait(self.driver, request.wait_time).until(
                request.wait_until
            )

        if request.screenshot:
            request.meta['screenshot'] = self.driver.get_full_page_screenshot_as_png()

        if request.script:
            self.driver.execute_script(request.script)

        if request.cb_intercept:
            intercept_func = request.cb_intercept
            request.meta['intercept_data'] = intercept_func(driver)

        # poll for requests or page source, compare to previous page source
        # scroll to bottom of page (Only scroll to max height of X), poll again, scroll to top, poll again

        current_url = self.driver.current_url

        body = str.encode(self.driver.page_source)

        request.meta.update({'used_selenium': True})

        # build the redirect chain
        redirect_chain = []
        last_request_url = request.url
        if current_url != last_request_url:
            for sel_request in self.driver.requests:
                redirect_url = sel_request.response.headers.get('location')  # considered dirty for comparison, may contain ports that aren't included in the response url
                if sel_request.response.status_code in [300, 301, 302, 303, 304, 307] and not compare_urls(last_request_url, redirect_url):
                    last_request_url = clean_url(sel_request.response.headers.get('location'))
                    redirect_chain.append({
                        'request_url': sel_request.url,
                        'status_code': sel_request.response.status_code,
                        'redirect_location': last_request_url,
                        'request_headers': sel_request.headers,
                        'response_headers': sel_request.response.headers
                    })

        request.meta.update({'redirects': redirect_chain})

        # close the driver
        self.driver.quit()

        return HtmlResponse(
            current_url,
            body=body,
            encoding='utf-8',
            request=request
        )

    def spider_closed(self):
        """Shutdown the driver when spider is closed"""

        self.driver.quit()

