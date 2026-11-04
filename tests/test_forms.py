from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import unittest


class Inputs(HTMLParser):
    def __init__(self):super().__init__();self.numbers=[]
    def handle_starttag(self,tag,attrs):
        item=dict(attrs)
        if tag=='input' and item.get('type')=='number':self.numbers.append(item)


class FormDefaultsTests(unittest.TestCase):
    def test_numeric_defaults_can_be_submitted_without_opening_advanced_options(self):
        parser=Inputs()
        parser.feed((Path(__file__).resolve().parents[1]/'voz_estudio'/'static'/'index.html').read_text(encoding='utf-8'))
        self.assertGreater(len(parser.numbers),0)
        for item in parser.numbers:
            with self.subTest(field=item.get('id')):
                value=Decimal(item['value'])
                if 'min' in item:self.assertGreaterEqual(value,Decimal(item['min']))
                if 'max' in item:self.assertLessEqual(value,Decimal(item['max']))
                if item.get('step')!='any':
                    step=Decimal(item.get('step','1'))
                    base=Decimal(item.get('min',item.get('value','0')))
                    self.assertEqual((value-base)%step,0,'El valor inicial bloquea la validación HTML del formulario.')
