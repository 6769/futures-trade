# -*- coding: utf-8 -*-
# !/usr/bin/env python
"""
中国期货市场监控中心客户端

用于下载每日每月统计数据报表
"""
import os
import unittest
import logging
import datetime

import httpx
import ddddocr
from lxml import etree

logger = logging.getLogger(__name__)


class CfmmcClient:
    """
    投资者查询服务系统
    Futures Statements Query Service System

    https://investorservice.cfmmc.com/
    """
    TOP_URL = 'https://investorservice.cfmmc.com/'
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'

    def __init__(self, username, password):
        """"""
        self.username = username
        self.passwd = password
        self._ocr = ddddocr.DdddOcr(show_ad=False)
        self.debug = bool(os.environ.get('DEBUG'))
        self._session = httpx.Client(base_url=self.TOP_URL, headers={'User-Agent': self.UA},
                                     timeout=10, verify=not self.debug)
        self._current_page = None

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()

    def _process_verify_code(self):
        """
        https://investorservice.cfmmc.com/veriCode.do?t=1730569549569

        :return:
        """

        resp = self._session.get('/veriCode.do')
        code = self._ocr.classification(resp.content)
        logger.info('veriCode: %s', code)
        return code

    def _post_login_form(self, code) -> bool:
        """
org.apache.struts.taglib.html.TOKEN: 8be3, /html/body/form/div/input, <input type="hidden" name="org.apache.struts.taglib.html.TOKEN" value="8be3">
showSaveCookies:
userID: 000
password: 000
vericode: 000

        :param login_para:
        :return:
        """
        html = etree.HTML(self._current_page)
        input_value = html.xpath(self.csrf_xpath)

        login_para = {
            'userID': self.username,
            'password': self.passwd,
            'vericode': code,
            'org.apache.struts.taglib.html.TOKEN': input_value[0],
        }
        r = self._session.post('/login.do', data=login_para)
        isLogin = '验证码' not in r.text

        after_login = etree.HTML(r.text)
        login_failed = after_login.xpath("//span[contains(@class, 'error-msg')]")
        if login_failed:
            msg = login_failed[0].text.strip()
            logger.warning('login error msg: %s', msg)

        return isLogin

    def login(self):
        """"""

        self._switch_page('/')
        code = self._process_verify_code()

        return self._post_login_form(code)

    def logout(self):
        """
deleteCookies: N
logout: 退出系统
        :return:
        """
        r = self._session.post('/logout.do', data={
            'deleteCookies': 'N',
            'logout': '退出系统'
        })
        isLogout = '验证码' in r.text
        logger.info('logout: %s', isLogout)
        return isLogout

    def _switch_page(self, path: str):
        r = self._session.get(path)
        self._current_page = r.text

    csrf_xpath = "//input[contains(@name, 'org.apache.struts.taglib.html.TOKEN')]/@value"

    def _setup_para_remote(self, *args, **kwargs):
        """"""

        para = dict()
        para.update(kwargs)

        html = etree.HTML(self._current_page)
        input_value = html.xpath(self.csrf_xpath)
        para['org.apache.struts.taglib.html.TOKEN'] = input_value[0]

        r = self._session.post('/customer/setParameter.do', data=para)
        self._current_page = r.text

        if r.status_code >= 400:
            logger.warning('setup error: %s, %s', r, para)

    def download_daily(self, date: str = '', byType='trade') -> bytes:
        """
        下载每日交易数据xlsx
        https://investorservice.cfmmc.com/customer/setupViewCustomerDetailFromCompanyWithExcel.do?version=7

        tradeDate: 2024-09-30
        byType: trade

        :param date:
        :return:
        """
        self._switch_page('/customer/setupViewCustomerDetailFromCompanyAuto.do')
        if date:
            self._setup_para_remote(**{'tradeDate': date, 'byType': byType})
        r = self._session.get('/customer/setupViewCustomerDetailFromCompanyWithExcel.do?version=7', timeout=30)
        self._download_file_check(r)
        return r.content

    def _download_file_check(self, r: httpx.Response):
        h: str = r.headers.get('Content-Disposition')
        if not h:
            logger.error('not file:%s', r.url)
            raise FileNotFoundError(r.url)
        hasAttachment = 'attachment' in h.lower()
        if not hasAttachment:
            raise FileNotFoundError(r.url)

    def download_month(self, date: str = '', byType='trade') -> bytes:
        """
        下载每月交易数据xlsx
        https://investorservice.cfmmc.com/customer/setupViewCustomerMonthDetailFromCompanyWithExcel.do?version=7

        setup:
        tradeDate: 2024-09
        byType: trade

        :param date:
        :return:
        """
        self._switch_page('/customer/setupViewCustomerMonthDataFromCompanyAuto.do')
        if date:
            self._setup_para_remote(**{'tradeDate': date, 'byType': byType})
        r = self._session.get('/customer/setupViewCustomerMonthDetailFromCompanyWithExcel.do?version=7', timeout=100)
        self._download_file_check(r)
        return r.content


class CMFFTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import dotenv
        dotenv.load_dotenv('.env.cfmmc')

        logging.basicConfig(level=logging.INFO)
        # os.environ['DEBUG'] = '1'

    @unittest.skip
    def test_client_login_err(self):
        """"""
        c = CfmmcClient('1', '1')
        self.assertFalse(c.login())

    def test_download_all(self):
        """
        下载每日（月）交易数据例子
        """
        username = os.environ.get('CFFUSERNAME')
        passwd = os.environ.get('PASSWD')
        if not username or not passwd:
            self.fail('missing real username/passwd')

        c = CfmmcClient(username, passwd)
        self.assertTrue(c.login())

        r1 = c.download_daily()
        now = datetime.date.today()
        recentMonday = now - datetime.timedelta(days=now.weekday())

        r11 = c.download_daily(date=recentMonday.isoformat())
        # r2 = c.download_month()
        self.assertTrue(c.logout())

    def test_failed_download(self):
        """
        没有登录状态，下载文件触发类型检查异常
        :return:
        """
        c = CfmmcClient('username', 'passwd')
        with self.assertRaises(FileNotFoundError):
            c.download_daily()
