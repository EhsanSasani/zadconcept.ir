from datetime import date
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.template.loader import render_to_string

from main.persian_dates import format_persian_date, parse_persian_date
from main.studio_views import _period


class PersianPeriodTests(SimpleTestCase):
    def period(self, **params):
        with patch('main.studio_views.timezone.localdate', return_value=date(2026, 10, 6)):
            return _period(RequestFactory().get('/', {'period': 'custom', **params}))

    def test_digits_and_nowruz(self):
        for value in ('1405/01/01', '۱۴۰۵/۰۱/۰۱', '١٤٠٥/٠١/٠١'):
            self.assertEqual(parse_persian_date(value), date(2026, 3, 21))
        self.assertEqual(format_persian_date(date(2026, 10, 6)), '۱۴۰۵/۰۷/۱۴')

    def test_leap_day_and_invalid_dates(self):
        self.assertEqual(parse_persian_date('1403/12/30'), date(2025, 3, 20))
        for value in ('1404/12/30', '1405/07/31', '1405/13/01', '', '2026-10-06'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_persian_date(value)

    def test_jalali_range_and_gregorian_bookmark_have_identical_boundaries(self):
        jalali = self.period(start_jalali='۱۴۰۵/۰۷/۰۱', end_jalali='۱۴۰۵/۰۷/۱۴')
        legacy = self.period(start='2026-09-23', end='2026-10-06')
        for key in ('start', 'end', 'lower', 'upper'):
            self.assertEqual(jalali[key], legacy[key])
        self.assertEqual(jalali['choice'], 'custom')
        self.assertEqual(jalali['upper'].date(), date(2026, 10, 7))

    def test_invalid_ranges_show_feedback_and_preserve_input(self):
        for start, end in [('1405/07/15', '1405/07/15'), ('1405/07/14', '1405/07/01'),
                           ('1403/01/01', '1405/01/01'), ('1404/12/30', '1405/01/01')]:
            with self.subTest(start=start, end=end):
                period = self.period(start_jalali=start, end_jalali=end)
                self.assertEqual(period['choice'], '30')
                self.assertTrue(period['error'])
                self.assertEqual(period['input_start'], start)
                html = render_to_string('main/studio/partials/period.html', {'period': period})
                self.assertIn('role="alert"', html)
                self.assertIn('class="custom-period" open', html)

    def test_missing_end_cannot_fall_back_to_legacy_parameters(self):
        period = self.period(start_jalali='1405/07/01', start='2026-10-01', end='2026-10-06')
        self.assertTrue(period['error'])

    def test_quick_period_ignores_unfinished_custom_input(self):
        period = _period(RequestFactory().get('/', {'period': '7', 'start_jalali': 'bad'}))
        self.assertEqual(period['choice'], '7')
        self.assertFalse(period['error'])

    def test_form_is_shamsi_without_javascript(self):
        period = self.period(start='2026-10-06', end='2026-10-06')
        html = render_to_string('main/studio/partials/period.html', {'period': period})
        self.assertIn('value="۱۴۰۵/۰۷/۱۴"', html)
        self.assertNotIn('type="date"', html)
        self.assertIn('از تاریخ (شمسی)', html)
