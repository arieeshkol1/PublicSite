"""
trace_collector.py — Captures and structures Bedrock Agent trace events.
"""

import time
import json
import logging

logger = logging.getLogger(__name__)

MAX_TRACE_SIZE_BYTES = 50 * 1024  # 50KB limit


class TraceCollector:
    """Collects trace events from a Bedrock Agent EventStream and produces
    a structured trace object for audit storage."""

    def __init__(self):
        self._events = []
        self._tools_selected = []
        self._tool_invocations = []
        self._reasoning_steps = []

    def capture_event(self, event):
        """Capture a single trace event from the EventStream.

        Args:
            event: A dict from the EventStream containing a 'trace' key.
        """
        trace_data = event.get('trace', {}).get('trace', {})
        capture_time = time.time()

        self._events.append({
            'event_type': self._detect_event_type(trace_data),
            'timestamp': capture_time,
            'payload': trace_data,
        })

        # Process orchestration trace
        orch_trace = trace_data.get('orchestrationTrace', {})
        if orch_trace:
            self._process_orchestration_trace(orch_trace)

        # Process pre/post-processing traces (capture reasoning)
        pre_trace = trace_data.get('preProcessingTrace', {})
        if pre_trace:
            self._process_preprocessing_trace(pre_trace)

        post_trace = trace_data.get('postProcessingTrace', {})
        if post_trace:
            self._process_postprocessing_trace(post_trace)

    def _detect_event_type(self, trace_data):
        """Determine the type of trace event."""
        if 'orchestrationTrace' in trace_data:
            return 'orchestration'
        elif 'preProcessingTrace' in trace_data:
            return 'preProcessing'
        elif 'postProcessingTrace' in trace_data:
            return 'postProcessing'
        elif 'guardrailTrace' in trace_data:
            return 'guardrail'
        elif 'failureTrace' in trace_data:
            return 'failure'
        return 'unknown'

    def _process_orchestration_trace(self, orch_trace):
        """Extract tool invocations and reasoning from orchestration trace."""
        # Extract rationale (reasoning step)
        rationale = orch_trace.get('rationale', {})
        if rationale and rationale.get('text'):
            self._reasoning_steps.append(rationale['text'])

        # Extract model invocation input (reasoning step)
        model_input = orch_trace.get('modelInvocationInput', {})
        if model_input and model_input.get('text'):
            self._reasoning_steps.append(model_input['text'])

        # Extract invocation input (tool call)
        invocation_input = orch_trace.get('invocationInput', {})
        action_group_input = invocation_input.get('actionGroupInvocationInput', {})
        if action_group_input:
            tool_name = action_group_input.get('function', '') or action_group_input.get('actionGroupName', '')
            if tool_name:
                if tool_name not in self._tools_selected:
                    self._tools_selected.append(tool_name)

                self._tool_invocations.append({
                    'tool_name': tool_name,
                    'request_params': action_group_input.get('parameters', {}),
                    'response_data': None,  # Filled on observation
                    'duration_ms': 0,
                    '_start_time': time.time(),
                })

        # Extract observation (tool response)
        observation = orch_trace.get('observation', {})
        action_group_output = observation.get('actionGroupInvocationOutput', {})
        if action_group_output and self._tool_invocations:
            # Update the most recent invocation with response data
            last_invocation = self._tool_invocations[-1]
            if last_invocation['response_data'] is None:
                last_invocation['response_data'] = action_group_output.get('text', '')
                start = last_invocation.pop('_start_time', time.time())
                last_invocation['duration_ms'] = int((time.time() - start) * 1000)

    def _process_preprocessing_trace(self, pre_trace):
        """Extract reasoning from preprocessing trace."""
        model_output = pre_trace.get('modelInvocationOutput', {})
        parsed = model_output.get('parsedResponse', {})
        rationale = parsed.get('rationale')
        if rationale:
            self._reasoning_steps.append(rationale)

    def _process_postprocessing_trace(self, post_trace):
        """Extract reasoning from postprocessing trace."""
        model_output = post_trace.get('modelInvocationOutput', {})
        parsed = model_output.get('parsedResponse', {})
        if parsed and parsed.get('text'):
            self._reasoning_steps.append(parsed['text'])

    def build_structured_trace(self):
        """Produce the final structured trace object.

        Returns:
            dict with keys: tools_selected, tool_invocations, reasoning_steps
        """
        # Clean up internal tracking fields from invocations
        clean_invocations = []
        for inv in self._tool_invocations:
            clean_invocations.append({
                'tool_name': inv['tool_name'],
                'request_params': inv['request_params'],
                'response_data': inv.get('response_data'),
                'duration_ms': inv.get('duration_ms', 0),
            })

        return {
            'tools_selected': list(self._tools_selected),
            'tool_invocations': clean_invocations,
            'reasoning_steps': list(self._reasoning_steps),
        }


def serialize_trace(structured_trace):
    """Serialize the structured trace to JSON with 50KB size enforcement.

    If serialized trace exceeds 50KB, truncates tool_invocations response_data
    starting from the oldest invocation until it fits.

    Args:
        structured_trace: dict from TraceCollector.build_structured_trace()

    Returns:
        JSON string ≤ 50KB
    """
    serialized = json.dumps(structured_trace, default=str)
    original_size = len(serialized.encode('utf-8'))

    if original_size <= MAX_TRACE_SIZE_BYTES:
        return serialized

    # Truncation needed — remove response_data from oldest invocations first
    trace_copy = {
        'tools_selected': structured_trace['tools_selected'],
        'tool_invocations': [inv.copy() for inv in structured_trace['tool_invocations']],
        'reasoning_steps': structured_trace['reasoning_steps'],
        '_truncated': True,
        '_original_size_bytes': original_size,
    }

    for i in range(len(trace_copy['tool_invocations'])):
        trace_copy['tool_invocations'][i]['response_data'] = '[TRUNCATED]'
        serialized = json.dumps(trace_copy, default=str)
        if len(serialized.encode('utf-8')) <= MAX_TRACE_SIZE_BYTES:
            return serialized

    # If still too large after all response_data truncated, truncate reasoning
    trace_copy['reasoning_steps'] = trace_copy['reasoning_steps'][:3]
    serialized = json.dumps(trace_copy, default=str)
    if len(serialized.encode('utf-8')) <= MAX_TRACE_SIZE_BYTES:
        return serialized

    # Last resort: hard truncate
    return serialized[:MAX_TRACE_SIZE_BYTES]
