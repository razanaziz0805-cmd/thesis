import copy
import math
import unittest

from stage1.catalogue import KOELN_POLICY as DEFAULT_POLICY
from stage1.engine import Decision, aggregate, evaluate_combination, evaluate_design, groundwater, intervention_need, validate_policy


POLICY = {**DEFAULT_POLICY, 'profile_reviewed': True, 'profile_review_ref': 'TEST_REVIEW'}
DESIGN = 'rain_garden_infiltration'


def gw_evidence(clearance=1.2):
    return {
        'evidence_ref': 'TEST_SITE', 'protection_zone': 'OUTSIDE', 'receiving_ground_clean': True,
        'soil_infiltration_ok': True, 'runoff_quality_ok': True, 'aquifer_evidence_ok': True,
        'mounding_assessed_ok': True, 'neighbour_distance_m': 2., 'non_waterproof_basement_present': False,
        'design_groundwater_elevation_m': 0., 'groundwater_uncertainty_m': 0.,
        'module_base_elevation_m__' + DESIGN: clearance, 'vertical_datum': 'DHHN2016',
        'groundwater_scenario_id': 'HIGH', 'groundwater_standard_confirmed': True,
    }


def gw_rows(a, design=DESIGN, policy=POLICY):
    return groundwater(a, policy, design, 'DHHN2016', 'HIGH')


def rule(rows, key):
    return next(r for r in rows if r.rule_id == key)


class ThresholdTests(unittest.TestCase):
    def test_inclusive_flood_threshold(self):
        self.assertEqual(intervention_need(.10), 'YES')
        self.assertEqual(intervention_need(.099999), 'NO')
        self.assertEqual(intervention_need(.11), 'YES')

    def test_nodata_not_dry(self):
        for v in (None, -1, float('nan'), float('inf'), 'unknown'):
            self.assertEqual(intervention_need(v), 'UNKNOWN')
        self.assertEqual(intervention_need(0), 'NO')

    def test_changed_threshold(self):
        self.assertEqual(intervention_need(.10, .20), 'NO')
        for v in (-1, None, float('nan')):
            with self.assertRaises(ValueError):
                intervention_need(.1, v)


class GroundwaterTests(unittest.TestCase):
    def test_all_supported_evidence_passes_design_screen(self):
        self.assertEqual(aggregate(gw_rows(gw_evidence())), 'ADMISSIBLE')

    def test_preliminary_screen_is_never_final_admissibility(self):
        self.assertEqual(aggregate(gw_rows(gw_evidence(), None)), 'CONDITIONAL')

    def test_missing_is_conditional(self):
        self.assertEqual(aggregate(gw_rows({})), 'CONDITIONAL')

    def test_unknown_datum_never_passes_clearance(self):
        a = gw_evidence()
        a['vertical_datum'] = 'OTHER'
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')

    def test_wrong_groundwater_state_never_passes_clearance(self):
        a = gw_evidence()
        a['groundwater_scenario_id'] = 'NORMAL'
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')

    def test_specific_module_base_required(self):
        a = gw_evidence()
        del a['module_base_elevation_m__' + DESIGN]
        a['module_base_elevation_m'] = 10
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')

    def test_uncertainty_reduces_separation(self):
        a = gw_evidence(.65)
        a['groundwater_uncertainty_m'] = .2
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'FAIL')

    def test_negative_uncertainty_not_accepted(self):
        a = gw_evidence()
        a['groundwater_uncertainty_m'] = -.2
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')

    def test_exact_floor_requires_exception(self):
        a = gw_evidence(.5)
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')
        a.update(low_pollution_runoff=True, groundwater_exception_approved=True)
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'ADMISSIBLE')

    def test_below_floor_cannot_be_offset_by_exception(self):
        a = gw_evidence(.49999)
        a.update(low_pollution_runoff=True, groundwater_exception_approved=True)
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'FAIL')

    def test_preferred_boundary_and_missing_primary_confirmation(self):
        a = gw_evidence(1.)
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'ADMISSIBLE')
        a['groundwater_standard_confirmed'] = None
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')

    def test_protected_zone_and_contamination_fail(self):
        for field, value in [('protection_zone', 'II'), ('receiving_ground_clean', False)]:
            a = gw_evidence()
            a[field] = value
            self.assertEqual(aggregate(gw_rows(a)), 'FAIL')

    def test_outer_zone_is_not_automatic_permission(self):
        a = gw_evidence()
        a['protection_zone'] = 'IIIA'
        self.assertEqual(aggregate(gw_rows(a)), 'CONDITIONAL')
        a['outer_zone_authority_ok'] = True
        self.assertEqual(aggregate(gw_rows(a)), 'ADMISSIBLE')

    def test_recommended_basement_distance_conditional_not_hard_fail(self):
        a = gw_evidence()
        a.update(non_waterproof_basement_present=True, basement_distance_m=5.9)
        self.assertEqual(rule(gw_rows(a), 'basement_distance_m').status, 'CONDITIONAL')

    def test_neighbour_offset_hard_fail(self):
        a = gw_evidence()
        a['neighbour_distance_m'] = 1.999
        self.assertEqual(rule(gw_rows(a), 'neighbour_distance_m').status, 'FAIL')

    def test_rules_have_sources_closure_and_responsibility(self):
        for row in gw_rows({}):
            record = row.record()
            self.assertTrue(record['citation'])
            self.assertTrue(record['source_locator'])
            self.assertTrue(record['closure'])
            self.assertTrue(record['responsible_party'])

    def test_profile_transfers_require_review(self):
        with self.assertRaises(ValueError):
            validate_policy({**DEFAULT_POLICY, 'municipality': 'Essen'})

    def test_text_none_is_unknown_not_outside_protection(self):
        a = gw_evidence()
        a['protection_zone'] = 'None'
        self.assertEqual(rule(gw_rows(a), 'protection_zone').status, 'CONDITIONAL')

    def test_review_switch_requires_boolean(self):
        with self.assertRaises(ValueError):
            validate_policy({'profile_reviewed': 'false'})

    def test_subtraction_at_exact_floor_is_not_spurious_fail(self):
        a = gw_evidence()
        a['design_groundwater_elevation_m'] = 99.1
        a['groundwater_uncertainty_m'] = .4
        a['module_base_elevation_m__' + DESIGN] = 100.
        self.assertEqual(rule(gw_rows(a), 'groundwater_clearance').status, 'CONDITIONAL')

    def test_lined_variant_does_not_inherit_infiltration_prohibition(self):
        a = {'protection_zone': 'II', 'land_type': 'open_space'}
        rows = evaluate_design(a, 'rain_garden_lined', POLICY)
        self.assertNotIn('protection_zone', [r.rule_id for r in rows])
        self.assertEqual(rule(rows, 'groundwater_infiltration_rules').status, 'NOT_APPLICABLE')
        self.assertIn('groundwater_structural_risk_ok', [r.rule_id for r in rows])


class CombinationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [Decision('test_rule', 'ADMISSIBLE', 'Test', 'true', 'true', 'THESIS', 'TEST', 'TEST', '')]
        self.evaluations = {('a', 'green_roof'): self.rows, ('b', 'tree_trench_lined'): self.rows}
        self.units = {'a': {'area_m2': 100}, 'b': {'area_m2': 100}}
        self.combo = {
            'id': 'test', 'evidence_ref': 'TEST',
            'modules': [
                {'unit_id': 'a', 'design': 'green_roof', 'module_id': 'm1', 'footprint_id': 'f1', 'allocated_area_m2': 100, 'source_id': 'roof', 'source_fraction': 1},
                {'unit_id': 'b', 'design': 'tree_trench_lined', 'module_id': 'm2', 'footprint_id': 'f2', 'allocated_area_m2': 100, 'source_id': 'roof', 'source_fraction': 0}],
            'links': [{'from': 'm1', 'to': 'm2'}],
            **{k: True for k in ['layout_verified', 'hydraulic_link_verified', 'shared_source_accounting_verified', 'shared_storage_accounting_verified', 'outlet_capacity_verified', 'ownership_operation_verified']},
        }

    def evaluate(self):
        return evaluate_combination(self.combo, self.evaluations, self.units)

    def test_verified_combination_passes_spatial_screen(self):
        self.assertEqual(aggregate(self.evaluate()), 'ADMISSIBLE')

    def test_unverified_routing_stays_conditional(self):
        self.combo['hydraulic_link_verified'] = None
        self.assertEqual(aggregate(self.evaluate()), 'CONDITIONAL')

    def test_combination_evidence_reference_required(self):
        self.combo['evidence_ref'] = None
        self.assertEqual(aggregate(self.evaluate()), 'CONDITIONAL')

    def test_failed_member_cannot_be_compensated(self):
        self.evaluations[('b', 'tree_trench_lined')] = [Decision('fail', 'FAIL', 'unsafe', None, 'safe', 'THESIS', 'TEST', 'TEST', 'Redesign')]
        self.assertEqual(aggregate(self.evaluate()), 'FAIL')

    def test_duplicate_source_credit_fails(self):
        self.combo['modules'][1]['source_fraction'] = .1
        self.assertEqual(rule(self.evaluate(), 'source_budget_roof').status, 'FAIL')

    def test_insufficient_space_fails(self):
        self.combo['modules'][1]['allocated_area_m2'] = 101
        self.assertEqual(rule(self.evaluate(), 'space_budget_b').status, 'FAIL')

    def test_same_footprint_fails(self):
        self.combo['modules'][1]['footprint_id'] = 'f1'
        self.assertEqual(rule(self.evaluate(), 'overlapping_footprint').status, 'FAIL')

    def test_missing_links_conditional_and_wrong_endpoint_fails(self):
        self.combo['links'] = []
        self.assertEqual(rule(self.evaluate(), 'hydraulic_link_graph').status, 'CONDITIONAL')
        self.combo['links'] = [{'from': 'm1', 'to': 'missing'}]
        self.assertEqual(rule(self.evaluate(), 'hydraulic_link_graph').status, 'FAIL')

    def test_shared_storage_is_not_created_twice(self):
        self.combo['shared_storage'] = [{'id': 'tank', 'capacity_m3': 10, 'allocations_m3': [6, 6]}]
        self.assertEqual(rule(self.evaluate(), 'shared_storage_tank').status, 'FAIL')


if __name__ == '__main__':
    unittest.main()
