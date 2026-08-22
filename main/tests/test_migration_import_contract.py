from importlib import import_module

from django.test import SimpleTestCase


class MigrationImportPathContractTests(SimpleTestCase):
    def test_serialized_model_symbols_keep_main_models_contract(self):
        serialized_symbols = (
            "category_cover_upload_to",
            "event_cover_upload_to",
            "home_hero_upload_to",
            "home_hero_mobile_upload_to",
            "news_cover_upload_to",
            "product_cover_upload_to",
            "product_gallery_upload_to",
            "site_hero_upload_to",
            "site_hero_mobile_upload_to",
            "tag_cover_upload_to",
            "HERO_BUILTIN_FONT_CHOICES",
            "hero_font_upload_to",
            "HERO_POSITION_CHOICES",
            "HEX_COLOR_VALIDATOR",
            "validate_hero_font_file_size",
            "wedding_gallery_upload_to",
            "wedding_hero_upload_to",
            "wedding_hero_mobile_upload_to",
            "wedding_open_graph_upload_to",
            "wedding_proposal_bouquet_card_upload_to",
            "wedding_proposal_sweets_card_upload_to",
            "wedding_bridal_bouquet_card_upload_to",
            "wedding_car_card_upload_to",
            "wedding_collection_hero_upload_to",
            "wedding_collection_hero_mobile_upload_to",
        )
        serialized_callbacks = (
            "category_cover_upload_to",
            "event_cover_upload_to",
            "home_hero_upload_to",
            "home_hero_mobile_upload_to",
            "news_cover_upload_to",
            "product_cover_upload_to",
            "product_gallery_upload_to",
            "site_hero_upload_to",
            "site_hero_mobile_upload_to",
            "tag_cover_upload_to",
            "hero_font_upload_to",
            "validate_hero_font_file_size",
            "wedding_gallery_upload_to",
            "wedding_hero_upload_to",
            "wedding_hero_mobile_upload_to",
            "wedding_open_graph_upload_to",
            "wedding_proposal_bouquet_card_upload_to",
            "wedding_proposal_sweets_card_upload_to",
            "wedding_bridal_bouquet_card_upload_to",
            "wedding_car_card_upload_to",
            "wedding_collection_hero_upload_to",
            "wedding_collection_hero_mobile_upload_to",
        )
        models_module = import_module("main.models")

        for symbol in serialized_symbols:
            with self.subTest(symbol=symbol):
                self.assertTrue(
                    hasattr(models_module, symbol),
                    f"main.models.{symbol} must remain importable for migrations",
                )

        for symbol in serialized_callbacks:
            with self.subTest(callback=symbol):
                callback = getattr(models_module, symbol)
                self.assertEqual(callback.__module__, "main.models")
