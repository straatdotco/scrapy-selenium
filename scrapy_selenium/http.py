"""This module contains the ``SeleniumRequest`` class"""

from scrapy import Request


class SeleniumRequest(Request):
    """Scrapy ``Request`` subclass providing additional arguments"""

    def __init__(self, wait_time=None, wait_until=None, screenshot=False, script=None, cb_intercept=None, infinite_scroll=False, proxy=False, timeout=None, *args, **kwargs):
        """Initialize a new selenium request

        Parameters
        ----------
        wait_time: int
            The number of seconds to wait.
        wait_until: method
            One of the "selenium.webdriver.support.expected_conditions". The response
            will be returned until the given condition is fulfilled.
        screenshot: bool
            If True, a screenshot of the page will be taken and the data of the screenshot
            will be returned in the response "meta" attribute.
        script: str
            JavaScript code to execute.
        cb_intercept: method
            a python function which intercepts and interacts with the selenium request acting on the selenium driver.
            will return an object to meta['intercept_data']
            also acting on the driver changes what is returned to the response object by scrapy selenium
        infinite_scroll: int | bool
            Pass either an int or Bool, if it evaluates to true it'll infinite scroll to a max of 20000px, else int sets the max.
        proxy: bool
            if true, requests are proxied. Defaults to False
        timeout: int
            overrides the default timeout if it needs to be configured on a per domain/per request basis
        """

        self.wait_time = wait_time
        self.wait_until = wait_until
        self.screenshot = screenshot
        self.script = script
        self.cb_intercept = cb_intercept
        self.infinite_scroll = infinite_scroll
        self.proxy = proxy
        self.timeout = timeout

        super().__init__(*args, **kwargs)
