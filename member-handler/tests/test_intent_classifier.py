"""
Unit tests for the Intent Classifier module.

Tests keyword-based classification of user questions into target categories.
Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5
"""
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from intent_classifier import (
    _classify_intent,
    get_apis_for_intent,
    CATEGORY_API_MAPPING,
    CATEGORY_KEYWORDS,
)


class TestClassifyIntent:
    """Tests for _classify_intent function."""

    # --- Requirement 9.1: Classification into correct categories ---

    def test_ec2_question(self):
        """EC2-specific question should classify to ec2."""
        result = _classify_intent('What are my EC2 instance types?')
        assert 'ec2' in result

    def test_rds_question(self):
        """RDS-specific question should classify to rds."""
        result = _classify_intent('Show me RDS instances')
        assert result == {'rds'}

    def test_s3_question(self):
        """S3-specific question should classify to s3."""
        result = _classify_intent('Tell me about S3 buckets')
        assert result == {'s3'}

    def test_lambda_question(self):
        """Lambda-specific question should classify to lambda."""
        result = _classify_intent('How many Lambda invocations do I have?')
        assert 'lambda' in result

    def test_cost_general_question(self):
        """General cost question should classify to cost-general."""
        result = _classify_intent('What is my total monthly bill?')
        assert result == {'cost-general'}

    def test_network_question(self):
        """Network-specific question should classify to network."""
        result = _classify_intent('Show NAT gateway costs')
        assert 'network' in result

    def test_storage_question(self):
        """Storage-specific question should classify to storage."""
        result = _classify_intent('Show my EBS volumes')
        assert result == {'storage'}

    def test_compute_question(self):
        """Compute-specific question should classify to compute."""
        result = _classify_intent('rightsizing my EC2 fleet')
        assert result == {'compute'}

    # --- Requirement 9.2: EC2 classification skips unrelated APIs ---

    def test_ec2_only_maps_to_ec2_apis(self):
        """EC2-only intent should map to Cost Explorer + EC2 + CloudWatch only."""
        apis = get_apis_for_intent({'ec2'})
        assert 'cost_explorer' in apis
        assert 'ec2_describe_instances' in apis
        assert 'cloudwatch' in apis
        assert 'rds_describe_instances' not in apis
        assert 's3_list_buckets' not in apis
        assert 'nat_gateways' not in apis
        assert 'ebs_volumes' not in apis

    # --- Requirement 9.3: cost-general skips resource APIs ---

    def test_cost_general_no_resource_apis(self):
        """cost-general intent should only include cost_explorer."""
        apis = get_apis_for_intent({'cost-general'})
        assert apis == {'cost_explorer'}

    # --- Requirement 9.4: Ambiguous/multi-service returns 'all' ---

    def test_ambiguous_returns_all(self):
        """Ambiguous question with no keywords should return all."""
        result = _classify_intent('Hello, how are you?')
        assert result == {'all'}

    def test_empty_string_returns_all(self):
        """Empty string should return all."""
        result = _classify_intent('')
        assert result == {'all'}

    def test_whitespace_only_returns_all(self):
        """Whitespace-only input should return all."""
        result = _classify_intent('   ')
        assert result == {'all'}

    def test_multi_service_over_threshold_returns_all(self):
        """Question matching more than 2 categories returns all."""
        result = _classify_intent(
            'Show me compute and storage and network usage'
        )
        assert result == {'all'}

    def test_many_services_returns_all(self):
        """Question mentioning many services returns all."""
        result = _classify_intent(
            'How much am I spending on EC2 and RDS and S3 and Lambda and EBS?'
        )
        assert result == {'all'}

    # --- Requirement 9.5: Execution under 50ms ---

    def test_performance_under_50ms(self):
        """Classification must complete in under 50ms."""
        question = 'How much does my EC2 instances cost this month?'
        start = time.perf_counter()
        for _ in range(100):
            _classify_intent(question)
        elapsed_per_call = (time.perf_counter() - start) / 100 * 1000
        assert elapsed_per_call < 50, f'Took {elapsed_per_call:.2f}ms, limit is 50ms'

    # --- Multi-category logic ---

    def test_ec2_and_cost_returns_two_categories(self):
        """Question about EC2 cost should return both ec2 and cost-general."""
        result = _classify_intent('How much does EC2 cost?')
        assert result == {'ec2', 'cost-general'}

    def test_lambda_and_cost_returns_two_categories(self):
        """Question about Lambda cost should return both lambda and cost-general."""
        result = _classify_intent('How can I reduce Lambda costs?')
        assert result == {'lambda', 'cost-general'}

    def test_compute_absorbs_ec2(self):
        """When compute and ec2 are matched, ec2 is absorbed into compute."""
        # 'rightsizing' matches compute, 'EC2' matches ec2
        result = _classify_intent('rightsizing my EC2 fleet')
        assert result == {'compute'}
        assert 'ec2' not in result

    # --- get_apis_for_intent ---

    def test_get_apis_for_all_intent(self):
        """'all' intent returns all available APIs."""
        apis = get_apis_for_intent({'all'})
        assert apis == set(CATEGORY_API_MAPPING['all'])

    def test_get_apis_union_for_multiple_intents(self):
        """Multiple intents returns union of their API sets."""
        apis = get_apis_for_intent({'ec2', 'cost-general'})
        expected = set(CATEGORY_API_MAPPING['ec2']) | set(CATEGORY_API_MAPPING['cost-general'])
        assert apis == expected

    # --- Category API mapping completeness ---

    def test_all_categories_have_api_mapping(self):
        """Every keyword category should have a corresponding API mapping."""
        for category in CATEGORY_KEYWORDS:
            assert category in CATEGORY_API_MAPPING, f'{category} missing from API mapping'

    def test_all_mapping_includes_all_categories(self):
        """'all' mapping has correct entries."""
        assert 'all' in CATEGORY_API_MAPPING

    def test_category_api_mapping_has_cost_explorer(self):
        """Every category should include cost_explorer."""
        for category, apis in CATEGORY_API_MAPPING.items():
            assert 'cost_explorer' in apis, f'{category} missing cost_explorer'
