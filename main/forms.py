import re

from django import forms

from .models import LeadRequest


class LeadRequestForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        label="",
        widget=forms.HiddenInput(
            attrs={"autocomplete": "off", "tabindex": "-1", "aria-hidden": "true"}
        ),
    )

    class Meta:
        model = LeadRequest
        fields = [
            "full_name",
            "mobile",
            "lead_type",
            "delivery_window",
            "preferred_date",
            "event_location",
            "note",
        ]
        labels = {
            "full_name": "نام",
            "mobile": "شماره موبایل",
            "lead_type": "نوع درخواست",
            "delivery_window": "بازه زمانی تحویل",
            "preferred_date": "تاریخ",
            "event_location": "مکان",
            "note": "توضیح کوتاه",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "مثال: سارا احمدی"}),
            "mobile": forms.TextInput(attrs={"placeholder": "مثال: ۰۹۱۲۱۲۳۴۵۶۷", "inputmode": "numeric"}),
            "lead_type": forms.Select(),
            "delivery_window": forms.Select(),
            "preferred_date": forms.DateInput(attrs={"type": "date"}),
            "event_location": forms.TextInput(attrs={"placeholder": "مثال: مشهد، الهیه"}),
            "note": forms.Textarea(attrs={"rows": 3, "placeholder": "در حد یک توضیح کوتاه"}),
        }

    def __init__(self, *args, **kwargs):
        include_event_fields = kwargs.pop("include_event_fields", False)
        initial_lead_type = kwargs.pop("initial_lead_type", None)
        super().__init__(*args, **kwargs)

        self.fields["full_name"].required = True
        self.fields["mobile"].required = True
        self.fields["lead_type"].required = True
        self.fields["delivery_window"].required = True
        self.fields["note"].required = False
        self.fields["preferred_date"].required = False
        self.fields["event_location"].required = False

        if initial_lead_type:
            self.fields["lead_type"].initial = initial_lead_type

        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " lead-input").strip()

        self.include_event_fields = include_event_fields

    def clean_mobile(self):
        mobile = self.cleaned_data["mobile"].strip()
        digits = re.sub(r"\D", "", mobile)
        if len(digits) < 10 or len(digits) > 14:
            raise forms.ValidationError("شماره موبایل معتبر نیست.")
        return mobile

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("درخواست نامعتبر است.")
        return ""

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("delivery_window") == LeadRequest.DeliveryWindow.PICK_DATE and not cleaned.get("preferred_date"):
            self.add_error("preferred_date", "برای این بازه زمانی، تاریخ را انتخاب کنید.")

        if (
            self.include_event_fields
            or cleaned.get("lead_type") == LeadRequest.LeadType.EVENT
        ) and not cleaned.get("event_location"):
            self.add_error("event_location", "برای رویداد، مکان را وارد کنید.")

        return cleaned
