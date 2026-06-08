"""
Unit tests for the refactored lambda_function.py.

Validates:
- Legacy paths are resolved to vendor-neutral tool names (Req 7.1, 7.2)
- Tools route through provider_router (Req 2.1)
- Knowledge tools work without accountId (Req 10.5)
- Bedrock Agent response envelope is preserved
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import lambda_function


class TestLambdaHandler:
    """Tests for the main lambda_handler entry point."""

    def _make_event(self, api_path, parameters=None, action_group='TestGroup'):
        """Build a Bedrock Agent event."""
        params = []
        if parameters:
            for k, v in parameters.items():
                params.append({'name': k, 'value': v})
        return {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'POST',
            'parameters': params,
        }

    def test_response_envelope_structure(self):
        """The response always has messageVersion, response with actionGroup, apiPath, httpStatusCode."""
        event = self._make_event('/get-optimization-tips')

        with patch.object(lambda_function, '_get_optimization_tips', return_value={'tips': [], 'count': 0}):
            result = lambda_function.lambda_handler(event, None)

        assert result['messageVersion'] == '1.0'
        assert 'response' in result
        assert result['response']['actionGroup'] == 'TestGroup'
        assert result['response']['apiPath'] == '/get-optimization-tips'
        assert result['response']['httpStatusCode'] == 200
        assert 'responseBody' in result['response']
        assert 'application/json' in result['response']['responseBody']

    def test_legacy_path_routes_through_provider_router(self):
        """Legacy paths like /get-ec2-instances route via legacy_mapper → provider_router."""
        event = self._make_event('/get-ec2-instances', {
            'accountId': '123456789012',
            'memberEmail': 'user@example.com',
        })

        mock_result = {'instances': [], 'count': 0}
        with patch('provider_router.route_tool', return_value=mock_result) as mock_route:
            result = lambda_function.lambda_handler(event, None)

        mock_route.assert_called_once_with(
            'getComputeInstances',
            '123456789012',
            'user@example.com',
            {'accountId': '123456789012', 'memberEmail': 'user@example.com'}
        )
        body = json.loads(result['response']['responseBody']['application/json']['body'])
        assert body == mock_result

    def test_vendor_neutral_path_routes_through_provider_router(self):
        """Vendor-neutral paths pass through legacy_mapper unchanged and route via provider_router."""
        event = self._make_event('getComputeInstances', {
            'accountId': '123456789012',
            'memberEmail': 'user@example.com',
        })

        mock_result = {'instances': [{'instanceId': 'i-123'}], 'count': 1}
        with patch('provider_router.route_tool', return_value=mock_result) as mock_route:
            result = lambda_function.lambda_handler(event, None)

        mock_route.assert_called_once_with(
            'getComputeInstances',
            '123456789012',
            'user@example.com',
            {'accountId': '123456789012', 'memberEmail': 'user@example.com'}
        )

    def test_knowledge_tool_optimization_tips_no_account_needed(self):
        """getOptimizationTips works without accountId (Requirement 10.5)."""
        event = self._make_event('/get-optimization-tips', {'service': 'COMPUTE'})

        mock_tips = {'tips': [{'title': 'Right-size'}], 'count': 1}
        with patch.object(lambda_function, '_get_optimization_tips', return_value=mock_tips) as mock_fn:
            result = lambda_function.lambda_handler(event, None)

        mock_fn.assert_called_once_with('COMPUTE')
        body = json.loads(result['response']['responseBody']['application/json']['body'])
        assert body == mock_tips

    def test_knowledge_tool_pricing_data_no_account_needed(self):
        """getPricingData works without accountId (Requirement 10.5)."""
        event = self._make_event('/get-aws-pricing', {
            'serviceCode': 'AmazonEC2',
            'filters': 'instanceType=m5.large',
            'region': 'us-east-1',
        })

        mock_pricing = {'serviceCode': 'AmazonEC2', 'results': [], 'count': 0}
        with patch.object(lambda_function, '_get_pricing_data', return_value=mock_pricing) as mock_fn:
            result = lambda_function.lambda_handler(event, None)

        mock_fn.assert_called_once_with('AmazonEC2', 'instanceType=m5.large', 'us-east-1')
        body = json.loads(result['response']['responseBody']['application/json']['body'])
        assert body == mock_pricing

    def test_knowledge_tool_vendor_neutral_path(self):
        """Vendor-neutral getOptimizationTips path also works without accountId."""
        event = self._make_event('getOptimizationTips', {'service': 'STORAGE'})

        mock_tips = {'tips': [], 'count': 0}
        with patch.object(lambda_function, '_get_optimization_tips', return_value=mock_tips) as mock_fn:
            result = lambda_function.lambda_handler(event, None)

        mock_fn.assert_called_once_with('STORAGE')

    def test_vendor_neutral_getPricingData_path(self):
        """Vendor-neutral getPricingData path works without accountId."""
        event = self._make_event('getPricingData', {
            'service': 'AmazonS3',
            'region': 'eu-west-1',
        })

        mock_pricing = {'serviceCode': 'AmazonS3', 'results': [], 'count': 0}
        with patch.object(lambda_function, '_get_pricing_data', return_value=mock_pricing) as mock_fn:
            result = lambda_function.lambda_handler(event, None)

        # For getPricingData, serviceCode falls back to 'service' param
        mock_fn.assert_called_once_with('AmazonS3', '', 'eu-west-1')

    def test_non_knowledge_tool_without_account_returns_error(self):
        """Non-Knowledge tools without accountId return a helpful error."""
        event = self._make_event('getComputeInstances', {})

        result = lambda_function.lambda_handler(event, None)
        body = json.loads(result['response']['responseBody']['application/json']['body'])

        assert 'error' in body
        assert 'accountId' in body['error']
        assert 'guidance' in body

    def test_all_legacy_paths_resolve_correctly(self):
        """All 11 legacy paths should resolve to their neutral equivalents and route."""
        legacy_paths = {
            '/get-cost-data': 'getCostBreakdown',
            '/get-monthly-comparison': 'getMonthlyTrend',
            '/get-ec2-instances': 'getComputeInstances',
            '/get-rds-instances': 'getDatabaseInstances',
            '/get-lambda-functions': 'getServerlessFunctions',
            '/get-s3-buckets': 'getObjectStorage',
            '/get-ebs-volumes': 'getStorageVolumes',
            '/get-network-resources': 'getNetworkResources',
            '/get-budgets': 'getBudgets',
            '/get-finops-settings': 'getFinOpsSettings',
        }

        for legacy_path, expected_tool_name in legacy_paths.items():
            event = self._make_event(legacy_path, {
                'accountId': '111222333444',
                'memberEmail': 'test@test.com',
            })

            with patch('provider_router.route_tool', return_value={'ok': True}) as mock_route:
                lambda_function.lambda_handler(event, None)

            actual_tool_name = mock_route.call_args[0][0]
            assert actual_tool_name == expected_tool_name, (
                f"Legacy path {legacy_path} resolved to {actual_tool_name}, "
                f"expected {expected_tool_name}"
            )

    def test_httpMethod_preserved_in_response(self):
        """The httpMethod from the event is preserved in the response."""
        event = self._make_event('getOptimizationTips', {'service': ''})
        event['httpMethod'] = 'GET'

        with patch.object(lambda_function, '_get_optimization_tips', return_value={'tips': [], 'count': 0}):
            result = lambda_function.lambda_handler(event, None)

        assert result['response']['httpMethod'] == 'GET'

    def test_httpMethod_defaults_to_POST(self):
        """If httpMethod is missing, defaults to POST."""
        event = self._make_event('getOptimizationTips', {'service': ''})
        del event['httpMethod']  # The _make_event doesn't include it by default via get
        # Actually, the handler uses event.get('httpMethod', 'POST')
        event.pop('httpMethod', None)

        with patch.object(lambda_function, '_get_optimization_tips', return_value={'tips': [], 'count': 0}):
            result = lambda_function.lambda_handler(event, None)

        assert result['response']['httpMethod'] == 'POST'

    def test_unhandled_exception_returns_bedrock_envelope_with_error(self):
        """Unhandled exceptions are caught and returned in Bedrock Agent envelope (HTTP 200)."""
        event = self._make_event('getComputeInstances', {
            'accountId': '123',
            'memberEmail': 'user@test.com',
        })

        with patch('provider_router.route_tool', side_effect=RuntimeError("Unexpected crash")):
            result = lambda_function.lambda_handler(event, None)

        # Must still return Bedrock Agent envelope
        assert result['messageVersion'] == '1.0'
        assert result['response']['httpStatusCode'] == 200
        body = json.loads(result['response']['responseBody']['application/json']['body'])
        assert 'error' in body
        assert body['retryable'] is True
        assert 'guidance' in body
        # Must not expose internal error details
        assert 'Unexpected crash' not in body['error']

    def test_malformed_parameters_returns_bedrock_envelope(self):
        """Even if parameters parsing fails, returns Bedrock Agent envelope."""
        event = {
            'actionGroup': 'TestGroup',
            'apiPath': '/test',
            'httpMethod': 'POST',
            'parameters': [{'bad': 'format'}],  # Missing 'name' key
        }

        result = lambda_function.lambda_handler(event, None)

        # Must still return valid envelope
        assert result['messageVersion'] == '1.0'
        assert result['response']['httpStatusCode'] == 200
        body = json.loads(result['response']['responseBody']['application/json']['body'])
        assert 'error' in body


class TestExecuteTool:
    """Tests for the _execute_tool routing logic."""

    def test_knowledge_tool_getOptimizationTips(self):
        """getOptimizationTips routes to _handle_knowledge_tool."""
        with patch.object(lambda_function, '_get_optimization_tips', return_value={'tips': []}) as mock_fn:
            result = lambda_function._execute_tool('getOptimizationTips', '', '', {'service': 'COMPUTE'})
        mock_fn.assert_called_once_with('COMPUTE')

    def test_knowledge_tool_getPricingData(self):
        """getPricingData routes to _handle_knowledge_tool."""
        with patch.object(lambda_function, '_get_pricing_data', return_value={'results': []}) as mock_fn:
            result = lambda_function._execute_tool('getPricingData', '', '', {
                'serviceCode': 'AmazonEC2',
                'filters': 'x=y',
                'region': 'us-west-2',
            })
        mock_fn.assert_called_once_with('AmazonEC2', 'x=y', 'us-west-2')

    def test_non_knowledge_tool_routes_to_provider_router(self):
        """Non-Knowledge tools with accountId route through provider_router."""
        with patch('provider_router.route_tool', return_value={'data': 'result'}) as mock_route:
            result = lambda_function._execute_tool(
                'getComputeInstances', '123456789012', 'user@example.com', {}
            )
        mock_route.assert_called_once_with('getComputeInstances', '123456789012', 'user@example.com', {})
        assert result == {'data': 'result'}

    def test_missing_account_for_non_knowledge_tool(self):
        """Non-Knowledge tools without accountId return error (not crash)."""
        result = lambda_function._execute_tool('getComputeInstances', '', '', {})
        assert 'error' in result
        assert 'accountId' in result['error']

    def test_missing_member_email_for_non_knowledge_tool(self):
        """Non-Knowledge tools without memberEmail return error."""
        result = lambda_function._execute_tool('getBudgets', '123456789012', '', {})
        assert 'error' in result
