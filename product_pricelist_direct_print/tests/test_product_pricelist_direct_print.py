# Copyright 2017 Carlos Dauden <carlos.dauden@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.base.tests.common import DISABLED_MAIL_CONTEXT


@tagged("post_install", "-at_install")
class TestProductPricelistDirectPrint(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, **DISABLED_MAIL_CONTEXT))
        # Set report layout to void to wizard selection layout crashes the test
        report_layout = cls.env.ref("web.report_layout_standard")
        main_company = cls.env.ref("base.main_company")
        main_company.external_report_layout_id = report_layout.view_id.id

        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "Pricelist for test",
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "applied_on": "3_global",
                            "percent_price": 5.00,
                            "compute_price": "percentage",
                        },
                    )
                ],
            }
        )
        cls.category = cls.env["product.category"].create({"name": "Test category"})
        cls.category_child = cls.env["product.category"].create(
            {"name": "Test category child", "parent_id": cls.category.id}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Product for test",
                "categ_id": cls.category.id,
                "default_code": "TESTPROD01",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Partner for test",
                "property_product_pricelist": cls.pricelist.id,
                "email": "test@test.com",
            }
        )
        cls.wiz_obj = cls.env["product.pricelist.print"]

    def test_defaults(self):
        wiz = self.wiz_obj.new()
        res = wiz.with_context(
            active_model="product.pricelist", active_id=self.pricelist.id
        ).default_get([])
        self.assertEqual(res["pricelist_id"], self.pricelist.id)
        res = wiz.with_context(
            active_model="product.pricelist.item",
            active_ids=self.pricelist.item_ids.ids,
        ).default_get([])
        self.assertEqual(res["pricelist_id"], self.pricelist.id)
        res = wiz.with_context(
            active_model="res.partner",
            active_id=self.partner.id,
            active_ids=[self.partner.id],
        ).default_get([])
        self.assertEqual(
            res["pricelist_id"], self.partner.property_product_pricelist.id
        )
        res = wiz.with_context(
            active_model="product.template", active_ids=self.product.product_tmpl_id.ids
        ).default_get([])
        self.assertEqual(
            res["product_tmpl_ids"][0][2], self.product.product_tmpl_id.ids
        )
        res = wiz.with_context(
            active_model="product.product", active_ids=self.product.ids
        ).default_get([])
        self.assertEqual(res["product_ids"][0][2], self.product.ids)
        self.assertTrue(res["show_variants"])
        with self.assertRaises(ValidationError):
            wiz.print_report()
        wiz.show_sale_price = True
        res = wiz.print_report()
        self.assertIn("report_name", res)

    def test_action_pricelist_send_multiple_partner(self):
        partner_2 = self.env["res.partner"].create(
            {
                "name": "Partner for test 2",
                "property_product_pricelist": self.pricelist.id,
                "email": "test2@test.com",
            }
        )
        wiz = self.wiz_obj.with_context(
            active_model="res.partner", active_ids=[self.partner.id, partner_2.id]
        ).create({})
        wiz.action_pricelist_send()

    def test_last_ordered_products(self):
        SaleOrder = self.env["sale.order"]
        product2 = self.env["product.product"].create(
            {
                "name": "Product2 for test",
                "categ_id": self.category.id,
                "default_code": "TESTPROD02",
            }
        )
        so = self.env["sale.order"].new(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": self.product.name,
                            "product_id": self.product.id,
                            "product_uom_qty": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "price_unit": 1000.00,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": product2.name,
                            "product_id": product2.id,
                            "product_uom_qty": 10.0,
                            "product_uom_id": product2.uom_id.id,
                            "price_unit": 300.00,
                        },
                    ),
                ],
            }
        )
        sale_order = SaleOrder.create(so._convert_to_write(so._cache))
        sale_order.action_confirm()

        wiz = self.wiz_obj.with_context(
            active_model="res.partner", active_ids=self.partner.ids
        ).create({"last_ordered_products": 2})
        products = wiz.get_last_ordered_products_to_print()
        self.assertEqual(len(products), 2)

        wiz = self.wiz_obj.with_context(
            active_model="res.partner", active_ids=self.partner.ids
        ).create({"last_ordered_products": 1})
        products = wiz.get_last_ordered_products_to_print()
        self.assertEqual(len(products), 1)

    def test_show_only_defined_products(self):
        self.pricelist.item_ids.write(
            {"applied_on": "0_product_variant", "product_id": self.product.id}
        )
        wiz = self.wiz_obj.with_context(
            active_model="product.pricelist",
            active_id=self.pricelist.id,
        ).create({})
        wiz.show_only_defined_products = True
        wiz.show_variants = True
        products = wiz.get_products_to_print()
        self.assertIn(products, self.pricelist.item_ids.mapped("product_id"))
        self.pricelist.item_ids.write(
            {"applied_on": "2_product_category", "categ_id": self.category.id}
        )
        wiz.show_only_defined_products = True
        wiz.show_variants = True
        products = wiz.get_products_to_print()
        self.assertIn(self.product, products)

    def test_parent_categories(self):
        product_category_child = self.env["product.template"].create(
            {
                "name": "Product for test 2",
                "categ_id": self.category_child.id,
                "default_code": "TESTPROD02",
            }
        )
        self.pricelist.item_ids.write(
            {"applied_on": "2_product_category", "categ_id": self.category_child.id}
        )
        wiz = self.wiz_obj.with_context(
            active_model="product.pricelist",
            active_id=self.pricelist.id,
        ).create({})
        wiz.max_categ_level = 1
        groups = wiz.get_groups_to_print()
        product_ids = False
        for group in groups:
            if group["group_name"] == "Test category":
                product_ids = group["products"]
        self.assertTrue(product_ids)
        self.assertIn(product_category_child.id, product_ids.ids)

    def test_report(self):
        wiz = self.wiz_obj.with_context(
            active_model="product.pricelist",
            active_id=self.pricelist.id,
        ).create({})
        # Print PDF
        report_pdf = self.env.ref(
            "product_pricelist_direct_print.action_report_product_pricelist"
        )._render_qweb_pdf(
            "product_pricelist_direct_print.report_product_pricelist", wiz.ids
        )
        self.assertGreaterEqual(len(report_pdf[0]), 1)

    def test_compute_product_price_vat(self):
        tax = self.env["account.tax"].create(
            {
                "name": "Tax 10",
                "amount": 10.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
            }
        )
        self.product.taxes_id = [(6, 0, tax.ids)]
        wiz = self.wiz_obj.with_context(product=self.product).create(
            {"vat_mode": "vat_excl", "pricelist_id": self.pricelist.id}
        )
        self.assertIsInstance(wiz.product_price, float)
        self.product.list_price = 100.0
        wiz._compute_product_price()
        wiz.vat_mode = "vat_incl"
        wiz._compute_product_price()
        wiz.vat_mode = False
        wiz._compute_product_price()

    def test_default_get_scenarios(self):
        res = self.wiz_obj.with_context(
            active_model="res.partner",
            active_id=self.partner.id,
            active_ids=[self.partner.id],
        ).default_get(["pricelist_id", "partner_ids"])
        self.assertEqual(
            res["pricelist_id"], self.partner.property_product_pricelist.id
        )
        item = self.pricelist.item_ids[0]
        res = self.wiz_obj.with_context(
            active_model="product.pricelist.item", active_ids=item.ids
        ).default_get(["pricelist_id"])
        self.assertEqual(res["pricelist_id"], self.pricelist.id)

    def test_mailing_actions(self):
        wiz = self.wiz_obj.create(
            {
                "partner_ids": [(6, 0, self.partner.ids)],
                "pricelist_id": self.pricelist.id,
            }
        )
        res = wiz.action_pricelist_send()
        self.assertEqual(res["res_model"], "mail.compose.message")
        partner2 = self.partner.copy({"name": "Partner 2", "email": "p2@test.com"})
        wiz.partner_ids = [(4, partner2.id)]
        wiz.action_pricelist_send()  # Should call send_batch

    def test_filtering_and_sorting(self):
        wiz = self.wiz_obj.create(
            {
                "pricelist_id": self.pricelist.id,
                "order_field": "name",
                "max_categ_level": 2,
                "last_categ_level_to_print": 1,
            }
        )
        self.assertEqual(wiz.get_group_name("Category / Subcategory"), " Subcategory")
        wiz.show_only_defined_products = True
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "2_product_category",
                "categ_id": self.category.id,
            }
        )
        domain = wiz.get_products_domain()
        self.assertTrue(
            any(leaf[0] == "categ_id" for leaf in domain if isinstance(leaf, tuple))
        )
        wiz.product_selling_date_threshold = fields.Datetime.now()
        domain_so = wiz._get_sale_order_domain(self.partner)
        self.assertTrue(
            any(
                leaf[0] == "date_order" for leaf in domain_so if isinstance(leaf, tuple)
            )
        )

    def test_grouping_logic(self):
        wiz = self.wiz_obj.create(
            {
                "pricelist_id": self.pricelist.id,
                "group_field": "categ_id",
            }
        )
        groups = wiz.get_groups_to_print()
        wiz.product_tmpl_ids = [(6, 0, self.product.product_tmpl_id.ids)]
        groups = wiz.get_groups_to_print()
        self.assertTrue(len(groups) > 0)
        self.assertEqual(groups[0]["group_name"], self.category.name)
