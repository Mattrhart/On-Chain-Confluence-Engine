import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "decoder",
    os.path.join(os.path.dirname(__file__), '..', 'app', 'decoder.py')
)
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
decode_secret_message = decoder.decode_secret_message


def test_decoder_hello():
    html = '''<html><body><table>
    <tr><th>x</th><th>char</th><th>y</th></tr>
    <tr><td>0</td><td>H</td><td>0</td></tr>
    <tr><td>1</td><td>E</td><td>0</td></tr>
    <tr><td>2</td><td>L</td><td>0</td></tr>
    <tr><td>3</td><td>L</td><td>0</td></tr>
    <tr><td>4</td><td>O</td><td>0</td></tr>
    </table></body></html>'''

    assert decode_secret_message(html=html) == 'HELLO'
