"""MURIEL criteria: exact limits, missing evidence, routing and protection."""
import unittest
from stage1.engine import evaluate_muriel, muriel_settings, aggregate


def metrics(**changes):
    return {'area_m2':3200.,'max_depth_m':.5,'boundary_incomplete':False,
            'receptor_distance_m':.5,'receptor_coverage_complete':True,
            'municipal_distance_m':10.,'municipal_coverage_complete':True,
            'destination_distance_m':20.,'destination_coverage_complete':True,
            'overlap_fraction':0.,'overlap_coverage_complete':True,
            'best_route_status':'ADMISSIBLE','evidence_ref':'TEST',**changes}


class MurielDecisionTests(unittest.TestCase):
    def test_area_and_depth_strict_boundaries(self):
        self.assertEqual(evaluate_muriel(metrics(area_m2=2000))[0],'BELOW_SCREEN')
        self.assertEqual(evaluate_muriel(metrics(max_depth_m=.30))[0],'BELOW_SCREEN')
        self.assertEqual(evaluate_muriel(metrics(area_m2=2000.01,max_depth_m=.30001))[0],'RETROFIT_CANDIDATE')

    def test_receptor_exact_one_metre_fails(self):
        self.assertEqual(evaluate_muriel(metrics(receptor_distance_m=1.))[0],'OUTSIDE_PRIORITY')

    def test_municipal_exact_fifty_metres_fails(self):
        self.assertEqual(evaluate_muriel(metrics(municipal_distance_m=50.))[0],'OUTSIDE_PRIORITY')

    def test_destination_exact_hundred_metres_included(self):
        self.assertEqual(evaluate_muriel(metrics(destination_distance_m=100.))[0],'RETROFIT_CANDIDATE')
        self.assertEqual(evaluate_muriel(metrics(destination_distance_m=100.001))[0],'NO_DESTINATION')

    def test_exact_seventy_percent_is_existing_retention(self):
        self.assertEqual(evaluate_muriel(metrics(overlap_fraction=.7))[0],'PROTECT_RETENTION')
        self.assertEqual(evaluate_muriel(metrics(overlap_fraction=.69999))[0],'RETROFIT_CANDIDATE')

    def test_protection_does_not_require_new_routing(self):
        planning,rows=evaluate_muriel(metrics(overlap_fraction=.75,best_route_status='FAIL'))
        self.assertEqual(planning,'PROTECT_RETENTION')
        self.assertEqual(next(d for d in rows if d.rule_id=='MURIEL_ROUTING').status,'NOT_APPLICABLE')

    def test_retention_protection_remains_visible_outside_priority_filter(self):
        planning,rows=evaluate_muriel(metrics(overlap_fraction=.8,receptor_distance_m=20.))
        self.assertEqual(planning,'PROTECT_RETENTION')
        self.assertEqual(aggregate(rows),'FAIL')  # Priority FAIL is not an instruction to remove the retention function.

    def test_nearby_space_without_route_is_investigation(self):
        self.assertEqual(evaluate_muriel(metrics(best_route_status='CONDITIONAL'))[0],'ROUTING_INVESTIGATION')

    def test_incompatible_assessed_route_requires_alternative(self):
        self.assertEqual(evaluate_muriel(metrics(best_route_status='FAIL'))[0],'ROUTE_UNSUITABLE')

    def test_missing_destination_inventory_not_no_destination(self):
        self.assertEqual(evaluate_muriel(metrics(destination_distance_m=None,destination_coverage_complete=False,overlap_coverage_complete=False))[0],'EVIDENCE_GAP')

    def test_complete_empty_destination_inventory_is_no_destination(self):
        self.assertEqual(evaluate_muriel(metrics(destination_distance_m=None))[0],'NO_DESTINATION')

    def test_incomplete_extent_not_definite_below_screen(self):
        planning,rows=evaluate_muriel(metrics(area_m2=100,boundary_incomplete=True))
        self.assertEqual(planning,'EVIDENCE_GAP')
        self.assertEqual(aggregate(rows),'CONDITIONAL')

    def test_partial_footprint_cannot_establish_failed_distance(self):
        planning,rows=evaluate_muriel(metrics(boundary_incomplete=True,receptor_distance_m=20.))
        self.assertEqual(planning,'EVIDENCE_GAP')
        self.assertEqual(next(d for d in rows if d.rule_id=='MURIEL_RECEPTOR').status,'CONDITIONAL')

    def test_groundwater_failure_not_surface_retention_failure(self):
        planning,rows=evaluate_muriel(metrics(overlap_fraction=.8,preliminary_infiltration_status='FAIL'))
        self.assertEqual(planning,'PROTECT_RETENTION')
        self.assertEqual(next(d for d in rows if d.rule_id=='MURIEL_GROUNDWATER_CROSSWALK').status,'NOT_APPLICABLE')

    def test_invalid_settings_rejected(self):
        for values in [{'min_area_m2':-1},{'protect_overlap_fraction':1.1},{'footprint_mode':'guess'}]:
            with self.assertRaises(ValueError): muriel_settings(values)

    def test_rule_citations_and_closure_present(self):
        _,rows=evaluate_muriel(metrics(best_route_status='CONDITIONAL'))
        for row in rows:
            self.assertTrue(row.record()['citation'])
            self.assertTrue(row.record()['source_locator'])
            self.assertTrue(row.responsible_party)
            if row.status=='CONDITIONAL': self.assertTrue(row.closure)

    def test_missing_inventory_reference_is_conditional(self):
        planning,rows=evaluate_muriel(metrics(evidence_ref='MISSING_SOURCE_REFERENCE'))
        self.assertEqual(planning,'EVIDENCE_GAP')
        self.assertEqual(aggregate(rows),'CONDITIONAL')
