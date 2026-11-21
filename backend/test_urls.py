import socket
import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.url_ingestion import extract, resolve_public, fetch_page

class URLTests(unittest.TestCase):
    def test_successful_fetch(self):
        public = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))
        with patch('app.url_ingestion.socket.getaddrinfo', return_value=[public]), patch('app.url_ingestion.socket.socket'), patch('app.url_ingestion.http.client.HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.headers.get_content_type.return_value = 'text/html'
            response.headers.get_content_charset.return_value = 'utf-8'
            response.getheader.return_value = 'identity'
            response.read1.side_effect = [b'<title>Test</title><p>Useful knowledge.</p>', b'']
            result = fetch_page('http://example.com')
            self.assertEqual(result['title'], 'Test')
            self.assertEqual(result['extracted_text'], 'Useful knowledge.')
            self.assertEqual(result['final_url'], 'http://example.com')

    def test_extract(self):
        title, text = extract('<title>Example</title><nav>Menu</nav><main><h1>Guide</h1><p>Hello <b>world</b>.</p><script>bad()</script></main>', 'text/html')
        self.assertEqual(title, 'Example')
        self.assertEqual(text, 'Guide\nHello world.')

    def test_schemes_and_credentials(self):
        for url in ('file:///etc/passwd', 'ftp://example.com', 'http://user:pass@example.com', 'http://example.com:8080'):
            with self.assertRaises(HTTPException) as error:
                resolve_public(url)
            self.assertEqual(error.exception.status_code, 422)

    def test_internal_addresses(self):
        for ip in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'):
            with patch('app.url_ingestion.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80))]):
                with self.assertRaises(HTTPException) as error:
                    resolve_public('http://example.com')
                self.assertEqual(error.exception.status_code, 422)

    def test_redirect_revalidation(self):
        public = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))
        private = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))
        with patch('app.url_ingestion.socket.getaddrinfo', side_effect=[[public], [private]]), patch('app.url_ingestion.socket.socket'), patch('app.url_ingestion.http.client.HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 302
            response.getheader.return_value = 'http://127.0.0.1/private'
            with self.assertRaises(HTTPException) as error:
                fetch_page('http://example.com')
            self.assertEqual(error.exception.status_code, 422)

    def test_upstream_failure(self):
        with patch('app.url_ingestion.socket.getaddrinfo', side_effect=socket.gaierror):
            with self.assertRaises(HTTPException) as error:
                fetch_page('http://invalid.example')
            self.assertEqual(error.exception.status_code, 502)

if __name__ == '__main__':
    unittest.main()
