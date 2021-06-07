"""This module contains the ``SeleniumMiddleware`` scrapy middleware"""

from importlib import import_module

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from selenium.webdriver.support.ui import WebDriverWait
import undetected_chromedriver as uc
from .http import SeleniumRequest


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
        if driver_name == 'uc':
            # uses https://github.com/ultrafunkamsterdam/undetected-chromedriver to bypass blocking
            options = uc.ChromeOptions()
            for argument in driver_arguments:
                options.add_argument(argument)
            self.driver = uc.Chrome(options=options)
        else:
            webdriver_base_path = f'selenium.webdriver.{driver_name}'

            driver_klass_module = import_module(f'{webdriver_base_path}.webdriver')
            driver_klass = getattr(driver_klass_module, 'WebDriver')

            driver_options_module = import_module(f'{webdriver_base_path}.options')
            driver_options_klass = getattr(driver_options_module, 'Options')

            driver_options = driver_options_klass()

            if browser_executable_path:
                driver_options.binary_location = browser_executable_path
            for argument in driver_arguments:
                driver_options.add_argument(argument)

            driver_kwargs = {
                'executable_path': driver_executable_path,
                'options': driver_options
            }

            # locally installed driver
            if driver_executable_path is not None:
                driver_kwargs = {
                    'executable_path': driver_executable_path,
                    'options': driver_options
                }
                self.driver = driver_klass(**driver_kwargs)
            # remote driver
            elif command_executor is not None:
                from selenium import webdriver
                capabilities = driver_options.to_capabilities()
                self.driver = webdriver.Remote(command_executor=command_executor, desired_capabilities=capabilities)

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings"""

        driver_name = crawler.settings.get('SELENIUM_DRIVER_NAME')
        driver_executable_path = crawler.settings.get('SELENIUM_DRIVER_EXECUTABLE_PATH')
        browser_executable_path = crawler.settings.get('SELENIUM_BROWSER_EXECUTABLE_PATH')
        command_executor = crawler.settings.get('SELENIUM_COMMAND_EXECUTOR')
        driver_arguments = crawler.settings.get('SELENIUM_DRIVER_ARGUMENTS')

        if driver_name is None:
            raise NotConfigured('SELENIUM_DRIVER_NAME must be set')

        if driver_executable_path is None and command_executor is None:
            raise NotConfigured('Either SELENIUM_DRIVER_EXECUTABLE_PATH '
                                'or SELENIUM_COMMAND_EXECUTOR must be set')

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

        if not isinstance(request, SeleniumRequest):
            return None

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
            request.meta['intercept_data'] = intercept_func(self.driver)

        # poll for requests or page source, compare to previous page source
        # scroll to bottom of page (Only scroll to max height of X), poll again, scroll to top, poll again

        body = str.encode(self.driver.page_source)

        # Expose the driver via the "meta" attribute
        # request.meta.update({'driver': self.driver})

        current_url = self.driver.current_url

        # close the driver to avoid memory leaks
        self.driver.close()

        return HtmlResponse(
            current_url,
            body=body,
            encoding='utf-8',
            request=request
        )

    def spider_closed(self):
        """Shutdown the driver when spider is closed"""

        self.driver.quit()

