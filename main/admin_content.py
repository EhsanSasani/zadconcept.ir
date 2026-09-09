"""Honest editing guidance for content consumed by the current public templates.

This registry intentionally excludes legacy templates. Adding a new slot requires
connecting it to a rendered template first; existing database rows are retained.
"""

import json

from django import forms
from django.urls import NoReverseMatch, reverse

from .models import PageContentBlock


def _slot(label, *fields):
    return {"label": label, "fields": fields}


PAGE_CONTENT_REGISTRY = {
    "about": {
        "hero": _slot("معرفی بالای صفحه؛ در نبود هیروی اختصاصی", "kicker", "body"),
        "story": _slot("داستان زاد", "kicker", "title", "body"),
        "worlds": _slot("جهان‌های زاد", "kicker", "title", "body"),
    },
    "contact": {
        "intro": _slot("معرفی تماس", "kicker", "title", "body"),
        "form": _slot("معرفی فرم تماس", "kicker", "title", "body"),
    },
    "faq": {"intro": _slot("معرفی پرسش‌های متداول", "kicker", "title", "body")},
    "occasions": {
        "intro": _slot("معرفی مناسبت‌ها", "kicker", "title", "body"),
        "empty": _slot("پیام نبود مناسبت؛ متن بر عنوان اولویت دارد", "body", "title"),
    },
    "subcategory": {
        "intro": _slot("معرفی مشترک زیردسته‌ها و ارسال روز", "title", "body"),
    },
    "product": {
        "before_order": _slot("قبل از ثبت سفارش", "kicker", "title", "body"),
        "related": _slot("عنوان محصولات مرتبط", "title"),
    },
    "event-detail": {
        "intro": _slot("عنوان کوتاه جزئیات ورکشاپ", "kicker"),
        "reserve": _slot("معرفی فرم رزرو ورکشاپ", "title", "body"),
    },
    "blog": {
        "intro": _slot("معرفی بلاگ", "body"),
        "empty": _slot("پیام نبود مطلب", "body"),
    },
    "mashhad": {
        "intro": _slot("معرفی صفحه اصلی مشهد", "body"),
        "selection": _slot("عنوان پیشنهادهای مشهد", "title"),
    },
}

PAGE_ROUTES = {
    "about": "about", "contact": "contact", "faq": "faq",
    "occasions": "occasions", "blog": "blog", "mashhad": "mashhad_hub",
}
FIELD_LABELS = {
    "kicker": "عنوان کوتاه", "title": "عنوان", "body": "متن",
    "cta_text": "متن دکمه", "cta_url": "لینک دکمه",
}


def _slot_help(page, key):
    slot = PAGE_CONTENT_REGISTRY.get(page, {}).get(key)
    if not slot:
        return "این جایگاه متعلق به محتوای قدیمی است و در قالب فعلی مصرف نمی‌شود؛ اطلاعات آن حفظ می‌شود."
    fields = "، ".join(FIELD_LABELS[field] for field in slot["fields"])
    return f"{slot['label']} — فیلدهای متصل: {fields}. سایر فیلدها ذخیره می‌شوند ولی نمایش ندارند."


class PageContentBlockAdminForm(forms.ModelForm):
    section_key = forms.ChoiceField(label="بخش صفحه")

    class Meta:
        model = PageContentBlock
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_pair = (
            (self.instance.page, self.instance.section_key)
            if self.instance.pk else None
        )
        page_labels = dict(PageContentBlock.Page.choices)
        pages = [(page, page_labels[page]) for page in PAGE_CONTENT_REGISTRY]
        keys = {}
        for slots in PAGE_CONTENT_REGISTRY.values():
            for key, slot in slots.items():
                keys.setdefault(key, slot["label"])
        if self._original_pair:
            original_page, original_key = self._original_pair
            if original_page not in PAGE_CONTENT_REGISTRY:
                pages.append((original_page, f"{page_labels.get(original_page, original_page)} — قدیمی"))
            if original_key not in keys:
                keys[original_key] = "جایگاه قدیمی؛ حفظ اطلاعات قبلی"
        self.fields["page"].widget.attrs["data-zad-slots"] = json.dumps(PAGE_CONTENT_REGISTRY, ensure_ascii=False)
        self.fields["page"].choices = [("", "صفحه را انتخاب کنید"), *pages]
        self.fields["section_key"].choices = [
            ("", "بخش را انتخاب کنید"),
            *((key, f"{key} — {label}") for key, label in keys.items()),
        ]
        page = self.data.get(self.add_prefix("page")) if self.is_bound else self.initial.get("page", "")
        key = self.data.get(self.add_prefix("section_key")) if self.is_bound else self.initial.get("section_key", "")
        self.fields["section_key"].help_text = (
            _slot_help(page, key) if page and key else
            "هر بخش فقط برای صفحه‌های مشخص فعال است؛ ترکیب انتخاب‌شده هنگام ذخیره بررسی می‌شود."
        )
        slots = PAGE_CONTENT_REGISTRY.get(page, {})
        if slots:
            self.fields["page"].help_text = "بخش‌های متصل این صفحه: " + "، ".join(slots)
        for field in ("cta_text", "cta_url"):
            self.fields[field].help_text = "در جایگاه‌های فعلی این پنل نمایش ندارد؛ مقدار قبلی بدون حذف حفظ می‌شود."
        self.fields["sort_order"].help_text = "ترتیب ثبت محتوا؛ ترتیب بخش‌های ثابت صفحه سایت را تغییر نمی‌دهد."

    def clean(self):
        cleaned = super().clean()
        page, key = cleaned.get("page"), cleaned.get("section_key")
        if not page or not key:
            return cleaned
        if key not in PAGE_CONTENT_REGISTRY.get(page, {}) and (page, key) != self._original_pair:
            self.add_error("section_key", "این بخش به صفحه انتخاب‌شده متصل نیست؛ یکی از بخش‌های فعال همان صفحه را انتخاب کنید.")
        return cleaned


def _public_url(route, **kwargs):
    if not route:
        return ""
    try:
        return reverse(route, kwargs=kwargs or None)
    except NoReverseMatch:
        return ""


def connection_guidance(model_name, obj=None):
    """Return autoescape-safe plain text and an optional local preview URL."""
    name = str(model_name).rsplit(".", 1)[-1].lower()
    text, route = "", None
    if name == "homeheroslide":
        text = "اسلایدهای قدیمی خانه؛ هیروی فعلی از سه تصویر ثابت استفاده می‌کند. تغییر این رکوردها اکنون تصویر، متن یا حرکت هیروی خانه را تغییر نمی‌دهد."
        route = "index"
    elif name == "sitehero":
        target = getattr(obj, "target_page", "")
        if target == "events":
            text = "در صفحه اصلی ورکشاپ فقط تصویر دسکتاپ و موبایل اولین هیروی فعال استفاده می‌شود؛ متن، فونت و اسلایدهای بعدی به این صفحه متصل نیستند. هیروی دارای اسلاگ برای جزئیات همان ورکشاپ است."
        else:
            text = "هیرو براساس صفحه مقصد و اسلاگ انتخاب می‌شود؛ هیروی اختصاصی فعال بر هیروی عمومی اولویت دارد. پشتیبانی از متن و تنظیمات به قالب صفحه بستگی دارد."
        route = {
            "flowers": "flowers", "bakery": "bakery", "gifts": "gifts",
            "about": "about", "contact": "contact", "faq": "faq",
            "events": "events", "occasions": "occasions", "blog": "blog",
            "mashhad": "mashhad_hub",
        }.get(target)
    elif name == "workshoppagecontent":
        text = "در طراحی فعلی فقط عنوان برنامه‌های آینده، عنوان حالت بدون برنامه و متن حالت بدون برنامه متصل‌اند. سایر فیلدها متعلق به طراحی قدیمی هستند و حفظ می‌شوند."
        route = "events"
    elif name == "pagecontentblock":
        text = _slot_help(getattr(obj, "page", ""), getattr(obj, "section_key", "")) if obj else "فقط بخش‌های متصل به قالب فعلی قابل ایجاد هستند. اطلاعات قدیمی حذف نمی‌شود؛ ترتیب ثبت، چیدمان صفحه را جابه‌جا نمی‌کند."
        route = PAGE_ROUTES.get(getattr(obj, "page", ""))
    elif name == "category":
        text = "نام، تصویر، توضیح، والد و وضعیت این دسته در کاتالوگ استفاده می‌شود. بعضی دسته‌های شناخته‌شده گل در صفحه استودیو ترتیب ثابت دارند؛ تغییر ترتیب عددی آن‌ها الزاماً ترتیب کارت‌ها را تغییر نمی‌دهد."
    elif name == "tag":
        text = "مناسبت‌های فعال در صفحات مناسبت و خانه نمایش دارند. تصویر و توضیح متصل‌اند؛ عنوان بعضی مناسبت‌های شناخته‌شده از متن ثابت قالب می‌آید و تغییر نام برچسب لزوماً عنوان کارت را تغییر نمی‌دهد."
        route = "occasions"
    elif name in {"contact", "sitesettings", "settings"}:
        text = "تلفن، آدرس و شبکه‌های اجتماعی از تنظیمات محیط اجرای سایت خوانده می‌شوند؛ در این پنل مدل قابل ویرایش برای آن‌ها وجود ندارد."
        route = "contact"
    return {"text": text, "url": _public_url(route)}
