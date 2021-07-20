"""This module contains the ``SeleniumMiddleware`` scrapy middleware"""

from importlib import import_module
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire.undetected_chromedriver.v2 import Chrome, ChromeOptions
import logging
from selenium.webdriver.remote.remote_connection import LOGGER as seleniumLogger
from urllib3.connectionpool import log as urllibLogger
from .http import SeleniumRequest
from urllib.parse import urlparse
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import WebDriverException
from scrapy.utils.request import request_fingerprint
from scrapy.utils.reqser import request_to_dict, request_from_dict
from scrapy.exceptions import IgnoreRequest

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
        options = ChromeOptions()
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
        self.driver = Chrome(options=options)

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

        def get_full_page_screenshot(driver):
            """
            Capture a full page screenshot in png
            Parameters
            ----------
            driver: the webdriver instance string
            Returns
            -------
            screenshot(str): the binary string of the screenshot png
            """
            original_size = driver.get_window_size()
            scroll_width = driver.execute_script('return document.body.parentNode.scrollWidth')
            scroll_height = driver.execute_script('return document.body.parentNode.scrollHeight')
            required_width = scroll_width if scroll_width < 1920 else 1920
            required_height = scroll_height if scroll_height < 20000 else 20000
            driver.set_window_size(required_width, required_height)
            screenshot = driver.find_element_by_tag_name('body').screenshot_as_png
            driver.set_window_size(original_size['width'], original_size['height'])
            return screenshot

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

        self.driver.set_page_load_timeout(10)
        try:
            self.driver.get(request.url)

            for cookie_name, cookie_value in request.cookies.items():
                self.driver.add_cookie(
                    {
                        'name': cookie_name,
                        'value': cookie_value
                    }
                )

            if request.wait_time:
                WebDriverWait(self.driver, request.wait_time)

            if request.wait_until:
                WebDriverWait(self.driver, request.wait_time).until(
                    request.wait_until
                )

            if request.screenshot:
                request.meta['screenshot'] = get_full_page_screenshot(self.driver)

            if request.script:
                self.driver.execute_script(request.script)

            if request.cb_intercept:
                intercept_func = request.cb_intercept
                request.meta['intercept_data'] = intercept_func(self.driver)

            # poll for requests or page source, compare to previous page source
            # scroll to bottom of page (Only scroll to max height of X), poll again, scroll to top, poll again

            current_url = self.driver.current_url

            body = str.encode(self.driver.page_source)

            request.meta.update({'used_selenium': True})

            # build the redirect chain
            req_dict = request_to_dict(request)
            redirect_chain = []
            last_request_url = request.url
            finding_redirects = True
            while finding_redirects:
                if len(self.driver.requests) < 1:
                    finding_redirects = False
                    response_status_code=500
                    response_headers=None
                for sel_request in self.driver.requests:
                    redirect_url = sel_request.response.headers.get('location')  # considered dirty for comparison, may contain ports that aren't included in the response url
                    if sel_request.response.status_code in [300, 301, 302, 303, 304, 307] and not compare_urls(last_request_url, redirect_url):
                        last_request_url = clean_url(sel_request.response.headers.get('location'))
                        req_dict['url'] = sel_request.url # we update the request url, so the cache key will be consistent
                        req_dict['body'] = sel_request.body # same as above, but the body
                        cache_key = request_fingerprint(request_from_dict(req_dict))
                        redirect_chain.append({
                            'cache_key': cache_key,
                            'request_url': sel_request.url,
                            'status_code': sel_request.response.status_code,
                            'redirect_location': last_request_url,
                            'request_headers': dict(sel_request.headers),
                            'response_headers': dict(sel_request.response.headers),
                            'response_body': sel_request.response.body.decode()
                        })
                    if sel_request.url == current_url:
                        req_dict['url'] = current_url # we update the request url, so the cache key will be consistent
                        req_dict['body'] = sel_request.body # same as above, but the body
                        response_headers = dict(sel_request.response.headers)
                        response_status_code = sel_request.response.status_code
                        cache_key = request_fingerprint(request_from_dict(req_dict))
                        redirect_chain.append({
                            'cache_key': cache_key,
                            'request_url': current_url,
                            'status_code': response_status_code,
                            'request_headers': dict(sel_request.headers),
                            'response_headers': response_headers,
                            'response_body': body
                        })

                        finding_redirects = False
                        break



            request.meta.update({'redirects': redirect_chain})

            self.driver.quit()

            # delete the encoding header because the body will not match gzip
            try:
                del response_headers['content-encoding']
            except:
                pass

            return HtmlResponse(
                current_url,
                body=body,
                status=response_status_code,
                headers=response_headers,
                encoding='utf-8',
                request=request # this can't be modified in middleware, so we have to deal with it, by using the redirect chain, returned in meta
            )

        except TimeoutException as e:
            self.driver.quit()
            raise IgnoreRequest(f'IgnoringRequest - {request.url} hit selenium timeout exception: {e}')
            # ToDo: how can this get returned to the spider to get processed... ie a site goes down, becomes buggy




    def spider_closed(self):
        """Shutdown the driver when spider is closed"""

        self.driver.quit()

