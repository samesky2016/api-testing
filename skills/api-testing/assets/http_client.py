#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP客户端 - 支持JSON格式的API测试
"""

import requests
import json
import logging
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTTPClient:
    """HTTP客户端"""

    def __init__(self, base_url: str = "", headers: Optional[Dict[str, str]] = None,
                 timeout: tuple = (10, 30)):
        """
        初始化HTTP客户端

        Args:
            base_url: 基础URL
            headers: 默认请求头
            timeout: 超时设置 (connect_timeout, read_timeout)
        """
        self.base_url = base_url.rstrip('/')
        self.default_headers = headers or {}
        self.timeout = timeout
        self.session = requests.Session()

    def _full_url(self, url: str) -> str:
        return url if url.startswith('http') else f"{self.base_url}{url}"

    def _merge_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {**self.default_headers}
        if extra:
            headers.update(extra)
        return headers

    def post(self, url: str, data: Any = None,
             headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """
        发送POST请求（JSON格式）

        Args:
            url: 请求路径或完整URL
            data: 请求体数据（dict）
            headers: 额外的请求头

        Returns:
            requests.Response 对象
        """
        full_url = self._full_url(url)
        req_headers = self._merge_headers(headers)
        req_headers.setdefault('Content-Type', 'application/json')

        body = json.dumps(data) if isinstance(data, dict) else data

        logger.info(f"POST {full_url}")
        logger.debug(f"Body: {body}")

        try:
            response = self.session.post(
                full_url,
                data=body,
                headers=req_headers,
                timeout=self.timeout
            )
            logger.info(f"Response: {response.status_code}")
            logger.debug(f"Response body: {response.text[:500]}")
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def get(self, url: str, params: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """
        发送GET请求

        Args:
            url: 请求路径或完整URL
            params: 查询参数
            headers: 额外的请求头

        Returns:
            requests.Response 对象
        """
        full_url = self._full_url(url)
        req_headers = self._merge_headers(headers)

        logger.info(f"GET {full_url}")
        logger.debug(f"Params: {params}")

        try:
            response = self.session.get(
                full_url,
                params=params,
                headers=req_headers,
                timeout=self.timeout
            )
            logger.info(f"Response: {response.status_code}")
            logger.debug(f"Response body: {response.text[:500]}")
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def put(self, url: str, data: Any = None,
            headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """发送PUT请求（JSON格式）"""
        full_url = self._full_url(url)
        req_headers = self._merge_headers(headers)
        req_headers.setdefault('Content-Type', 'application/json')

        body = json.dumps(data) if isinstance(data, dict) else data

        logger.info(f"PUT {full_url}")
        try:
            response = self.session.put(
                full_url, data=body, headers=req_headers, timeout=self.timeout
            )
            logger.info(f"Response: {response.status_code}")
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def delete(self, url: str, params: Optional[Dict[str, Any]] = None,
               headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """发送DELETE请求"""
        full_url = self._full_url(url)
        req_headers = self._merge_headers(headers)

        logger.info(f"DELETE {full_url}")
        try:
            response = self.session.delete(
                full_url, params=params, headers=req_headers, timeout=self.timeout
            )
            logger.info(f"Response: {response.status_code}")
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def close(self):
        """关闭会话"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
