import unittest

from rvb_vault.clipboard import resolve_template, template_variables


class TemplateTests(unittest.TestCase):
    def test_template_variables_are_unique_and_resolve(self):
        text = "ssh {{ user }}@{{ip}} then echo {{user}}"
        self.assertEqual(template_variables(text), ["user", "ip"])
        self.assertEqual(resolve_template(text, {"user": "root", "ip": "10.0.0.4"}), "ssh root@10.0.0.4 then echo root")


if __name__ == "__main__":
    unittest.main()

