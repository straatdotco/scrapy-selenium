"""This module contains the ``SeleniumMiddleware`` scrapy middleware"""

from importlib import import_module
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from scrapy.http import Response
# from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire.undetected_chromedriver.v2 import Chrome, ChromeOptions
import logging
from selenium.webdriver.remote.remote_connection import LOGGER as seleniumLogger
from selenium.webdriver.common.by import By
from urllib3.connectionpool import log as urllibLogger
from .http import SeleniumRequest
from urllib.parse import urlparse
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import WebDriverException
from scrapy.utils.request import request_fingerprint
from scrapy.utils.reqser import request_to_dict, request_from_dict
from scrapy.exceptions import IgnoreRequest
from time import sleep
import threading
import queue
import time


class SeleniumMiddleware:
    """Scrapy middleware handling the requests using selenium"""

    def __init__(self, driver_name, driver_executable_path, browser_executable_path, command_executor, driver_arguments, timeout, selenium_proxy):
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
        timeout: int
            the number of seconds before the request times out and returns a 622 error code
        selenium_proxy: str
            the string of the proxy like 127.0.0.1:3128 to be used when on the SeleniumRequest argument proxy=True
        """
        self.driver_name = driver_name
        self.driver_executable_path = driver_executable_path
        self.driver_arguments = driver_arguments
        self.browser_executable_path = browser_executable_path
        self.command_executor = command_executor
        self.timeout = timeout  # the page timeout
        self.selenium_proxy = selenium_proxy
        self.driver = None
        self.logger = logging.getLogger(__name__)

    def load_driver(self, proxy=False):
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

        if proxy and self.selenium_proxy:
            sw_options = {
                'proxy': {
                    'http': f'http://{self.selenium_proxy}',
                    'https': f'https://{self.selenium_proxy}',
                    'no_proxy': 'localhost,127.0.0.1'
                }
            }
        else:
            sw_options = {}

        #options.add_argument('--enable_cdp_event=True')
        # options.add_argument('--proxy-server=True')
        #options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        # raise the logging level for selenium-wire
        selenium_logger = logging.getLogger('seleniumwire')
        selenium_logger.setLevel(logging.ERROR)
        hpack_logger = logging.getLogger('hpack')
        hpack_logger.setLevel(logging.ERROR)
        seleniumLogger.setLevel(logging.WARNING)
        urllibLogger.setLevel(logging.WARNING)
        self.driver = Chrome(enable_cdp_events=True, options=options, seleniumwire_options=sw_options)

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings"""
        driver_name = crawler.settings.get('SELENIUM_DRIVER_NAME')
        driver_executable_path = crawler.settings.get('SELENIUM_DRIVER_EXECUTABLE_PATH')
        browser_executable_path = crawler.settings.get('SELENIUM_BROWSER_EXECUTABLE_PATH')
        command_executor = crawler.settings.get('SELENIUM_COMMAND_EXECUTOR')
        driver_arguments = crawler.settings.get('SELENIUM_DRIVER_ARGUMENTS')
        timeout = crawler.settings.get('SELENIUM_TIMEOUT', 20)
        selenium_proxy = crawler.settings.get('SELENIUM_PROXY', None)

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
            driver_arguments=driver_arguments,
            timeout=timeout,
            selenium_proxy=selenium_proxy
        )

        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)

        return middleware

    def process_request(self, request, spider):
        """Process a request using the selenium driver if applicable"""
        #breakpoint()
        start_time = time.time()
        idle_zero_time = start_time
        network_idle = threading.Event()
        idle_queue = queue.Queue()
        page_timeout = request.timeout if request.timeout else self.timeout
        wait_time = request.wait_time if isinstance(request.wait_time, int) else 5
        wait_time = wait_time if wait_time < page_timeout else page_timout
        max_wait_time = page_timeout  # The maximum amount of time to wait before proceeding

        def cdp_network_listen(msg):
            """
            when ever a network request is done we restart the start time
            """
            idle_zero_time = time.time()

        def watch_idle():
            while True:
                now_time = time.time()
                idle_time = now_time - idle_zero_time
                idle_queue.put(idle_time)
                if idle_time > wait_time:
                    break

        def blocking_idle(idle_queue, max_wait_time, wait_time):
            idle_time = 0
            total_time = time.time() - start_time
            while True:
                try:
                    idle_time = idle_queue.get(timeout=1)
                    if idle_time > wait_time:
                        network_idle.set()
                        break
                    elif total_time > max_wait_time:
                        network_idle.set()
                        # ToDo: this is actually a timeout raise exception... but grabbed by page_timeout ^
                        break
                except queue.Empty:
                    pass

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
            screenshot = driver.find_element(By.TAG_NAME, 'body').screenshot_as_png
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
        self.load_driver(proxy=request.proxy)

        self.driver.set_page_load_timeout(page_timeout)

        # devtools = self.driver.getDevTools()
        self.driver.add_cdp_listener('Page.loadEventFired', cdp_network_listen)
        self.driver.add_cdp_listener('Network.dataReceived', cdp_network_listen)
        self.driver.add_cdp_listener('Network.responseReceived', cdp_network_listen)
        self.driver.add_cdp_listener('Network.webSocketFrameReceived', cdp_network_listen)
        self.driver.add_cdp_listener('Network.webSocketFrameError', cdp_network_listen)

        try:
            self.driver.get(request.url)

            for cookie_name, cookie_value in request.cookies.items():
                self.driver.add_cookie(
                    {
                        'name': cookie_name,
                        'value': cookie_value
                    }
                )

            threading.Thread(target=blocking_idle, args=(idle_queue, max_wait_time, wait_time)).start()
            threading.Thread(target=watch_idle).start()
            network_idle.wait() # wait here until the network is idle

            if request.script:
                self.driver.execute_script(request.script)

            if request.cb_intercept:
                intercept_func = request.cb_intercept
                request.meta['intercept_data'] = intercept_func(self.driver)

            # poll for requests or page source, compare to previous page source
            # scroll to bottom of page (Only scroll to max height of X), poll again, scroll to top, poll again
            if request.infinite_scroll:
                max_height = request.infinite_scroll if type(request.infinite_scroll) in (float, int) else 20000
                last_height = self.driver.execute_script("return document.body.scrollHeight")
                while True:
                    network_idle.clear()
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    idle_zero_time = time.time()
                    threading.Thread(target=blocking_idle, args=(idle_queue, max_wait_time, wait_time)).start()
                    threading.Thread(target=watch_idle).start()
                    network_idle.wait()
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height or new_height > max_height:
                        break  # we're done the scrolling and break the loop
                    last_height = new_height

            if request.screenshot:
                request.meta['screenshot'] = get_full_page_screenshot(self.driver)

            current_url = self.driver.current_url



            body = str.encode(self.driver.page_source)
            request.meta.update({'synth_load_time': float(time.time() - start_time)})
            request.meta.update({'used_selenium': True})

            # build the redirect chain
            req_dict = request_to_dict(request, spider)
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
                        cache_key = request_fingerprint(request_from_dict(req_dict, spider))
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
                        cache_key = request_fingerprint(request_from_dict(req_dict, spider))
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
            try:
                del response_headers['Content-Encoding']
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
            if request.screenshot:
                request.meta['screenshot'] = get_full_page_screenshot(self.driver)
            self.driver.quit()
            self.logger.error(f'{request.url} hit a selenium timeout exception: {e}')
            return Response(request.url, status=622, request=request)  # return a 622 - this is the same as cloudflares timeout, but in our own 6xx code
        except Exception as e:
            self.driver.quit()
            self.logger.error(f'IgnoringRequest - {request.url} hit a unknown error: {e}')
            raise IgnoreRequest(f'IgnoringRequest - {request.url} because of scrapy-selenium error: {e}')




    def spider_closed(self):
        """Shutdown the driver when spider is closed"""

        self.driver.quit()

