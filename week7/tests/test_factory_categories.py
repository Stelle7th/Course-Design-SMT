"""Validate the saved category metadata against the project's source taxonomy."""
from collections import Counter
import csv
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / 'analysis/smat_layout_viz/tables'


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


class FactoryCategoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.categories = json.loads((ROOT/'week7/factory/categories.json').read_text(encoding='utf-8'))
        cls.factory = json.loads((ROOT/'week7/factory/factory-data.json').read_text(encoding='utf-8'))

    def test_every_equipment_group_has_exactly_one_category(self):
        mapping = self.categories['groupToCategory']
        groups = {e['group'] for e in self.factory['equipment']}
        self.assertEqual(set(mapping), groups)
        self.assertEqual(len(mapping), 108)
        self.assertEqual(len(self.factory['equipment']), 1116)
        definitions = {d['id'] for d in self.categories['definitions']}
        self.assertEqual(set(mapping.values()), definitions)
        self.assertNotIn('other', {name.lower() for name in definitions})

    def test_production_classification_and_colors_match_source_tables(self):
        mapping = self.categories['groupToCategory']
        summary = read_csv(TABLES/'workcenter_distribution_summary.csv')
        for row in summary:
            self.assertEqual(mapping[row['STNFAM']], row['area'], row['STNFAM'])
        palette = {d['id']: d['color'] for d in self.categories['definitions']}
        for row in read_csv(TABLES/'process_colors.csv'):
            self.assertEqual(palette[row['area']], row['color'])
        self.assertEqual(len(summary), 105)

    def test_counts_agree_with_independent_source_equipment_inventory(self):
        expected = Counter()
        for row in read_csv(TABLES/'workcenter_distribution_summary.csv'):
            expected[row['area']] += int(row['equipment_count'])
        raw = read_csv(TABLES/'raw/Equipment.csv')
        expected['Fixed_AMHS'] = sum(row['TOOL_GROUP'] in {'COMMIT', 'COMPLETE', 'STOCKER'} for row in raw)
        observed = Counter(self.categories['groupToCategory'][e['group']] for e in self.factory['equipment'])
        self.assertEqual(expected, observed)
        self.assertEqual(dict(expected), self.categories['counts'])
        self.assertEqual(expected['Fixed_AMHS'], 48)
        self.assertEqual(sum(expected.values())-expected['Fixed_AMHS'], 1068)

    def test_definitions_are_usable_as_a_distinct_legend(self):
        definitions = self.categories['definitions']
        self.assertEqual(len(definitions), 12)
        self.assertEqual(len({d['id'] for d in definitions}), len(definitions))
        self.assertEqual(len({d['color'].upper() for d in definitions}), len(definitions))
        for definition in definitions:
            self.assertRegex(definition['color'], r'^#[0-9A-Fa-f]{6}$')
            self.assertTrue(re.search(r'[\u4e00-\u9fff]', definition['label']))
            self.assertTrue(definition['aliases'])

    def test_fixed_facilities_and_existing_special_cases(self):
        mapping = self.categories['groupToCategory']
        for group in ['COMMIT', 'COMPLETE', 'STOCKER']:
            self.assertEqual(mapping[group], 'Fixed_AMHS')
        # These classifications are explicit in the original source tables.
        for group in ['EPI_36', 'EPI_38']:
            self.assertEqual(mapping[group], 'Implant')
        self.assertEqual(mapping['LithoTrack_FE_115'], 'Litho')
        self.assertEqual(mapping['Litho_REG_BE_63'], 'Litho_Met')
        self.assertEqual(mapping['DefMEt_FE_118'], 'Def_Met')


if __name__ == '__main__':
    unittest.main()
