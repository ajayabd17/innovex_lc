"""
Field Comparator: Deterministically compares outputs from 3 LLMs.
Identifies matching fields, conflicts, and missing values.
"""
import json
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class FieldComparator:
    """Compares field values across multiple LLM outputs."""
    
    def __init__(self):
        """Initialize field comparator."""
        self.comparison_results: Dict[str, Any] = {}
    
    def compare(self, outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare outputs from 3 LLMs field by field.
        
        Args:
            outputs: Dict with provider keys (e.g., 'fireworks', 'groq', 'baseten')
                    Each value is a dictionary of field: value pairs
        
        Returns:
            Comparison report with:
            - unanimous_fields: All available models agree
            - majority_fields: Most models agree
            - conflicting_fields: Models disagree
            - missing_fields: Field missing in some models
            - confidence_scores: Confidence in each field
        """
        self.comparison_results = {
            "unanimous_fields": {},      # All available providers agree
            "majority_fields": {},        # Most providers agree
            "conflicting_fields": {},     # Providers disagree
            "missing_fields": {},         # Missing in some outputs
            "field_distribution": {},     # What each model has
            "confidence_scores": {},      # 0.0-1.0 confidence
        }
        
        # Get all field names
        all_field_names = self._collect_all_fields(outputs)
        
        # Compare field by field
        for field_name in all_field_names:
            comparison = self._compare_field(field_name, outputs)
            self.comparison_results["field_distribution"][field_name] = comparison["present_in"]
            self._classify_field(field_name, comparison, outputs)
        
        return self.comparison_results
    
    def _collect_all_fields(self, outputs: Dict[str, Dict[str, Any]]) -> set:
        """Collect all unique field names from all outputs."""
        all_fields = set()
        for model_output in outputs.values():
            if isinstance(model_output, dict):
                all_fields.update(model_output.keys())
        return all_fields
    
    def _compare_field(self, field_name: str, 
                      outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare a single field across all models.
        
        Args:
            field_name: Field name to compare
            outputs: Model outputs
        
        Returns:
            Comparison data for the field
        """
        values = {}
        present_in = []
        
        for model_name, output in outputs.items():
            if isinstance(output, dict) and field_name in output:
                values[model_name] = output[field_name]
                present_in.append(model_name)
        
        # Normalize values for comparison (handle types, whitespace, etc.)
        normalized = self._normalize_for_comparison(values)
        
        # Count unique normalized values
        unique_values = {}
        for model, norm_val in normalized.items():
            val_key = json.dumps(norm_val, sort_keys=True, default=str)
            if val_key not in unique_values:
                unique_values[val_key] = []
            unique_values[val_key].append(model)
        
        return {
            "field_name": field_name,
            "values": values,
            "normalized": normalized,
            "unique_values": unique_values,
            "present_in": present_in,
            "missing_from": self._get_missing_models(present_in, outputs),
            "agreement_count": len(unique_values),  # 1 = unanimous, 3 = all different
        }
    
    def _normalize_for_comparison(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize values for comparison.
        
        Args:
            values: Dict of model: value pairs
        
        Returns:
            Normalized dict
        """
        normalized = {}
        for model, value in values.items():
            if value is None:
                normalized[model] = None
            elif isinstance(value, str):
                # Lowercase and strip whitespace for string comparison
                normalized[model] = value.lower().strip()
            elif isinstance(value, (int, float)):
                # Keep numeric as-is
                normalized[model] = value
            elif isinstance(value, bool):
                normalized[model] = value
            elif isinstance(value, list):
                # Sort lists for comparison
                try:
                    normalized[model] = sorted(value)
                except TypeError:
                    normalized[model] = value
            else:
                normalized[model] = value
        
        return normalized
    
    def _get_missing_models(self, present_in: List[str], outputs: Dict[str, Dict[str, Any]]) -> List[str]:
        """Get list of models that didn't provide this field."""
        all_models = set(outputs.keys())
        return list(all_models - set(present_in))
    
    def _classify_field(self, field_name: str, comparison: Dict[str, Any],
                       outputs: Dict[str, Dict[str, Any]]) -> None:
        """
        Classify field comparison result.
        
        Args:
            field_name: Field name
            comparison: Comparison data
            outputs: Original model outputs
        """
        agreement_count = comparison["agreement_count"]
        present_count = len(comparison["present_in"])
        total_models = len(outputs)
        
        # Unanimous: all configured providers agree and all present
        if agreement_count == 1 and present_count == total_models:
            value = comparison["values"][comparison["present_in"][0]]
            confidence = 1.0
            self.comparison_results["unanimous_fields"][field_name] = value
            self.comparison_results["confidence_scores"][field_name] = confidence
        
        # Majority/conflict: at least 2 providers present
        elif present_count >= 2:
            self._handle_majority_or_conflict(
                field_name, comparison, agreement_count, present_count
            )
        
        # Missing: field not in all outputs
        else:
            self._handle_missing_field(field_name, comparison)
    
    def _handle_majority_or_conflict(self, field_name: str, 
                                     comparison: Dict[str, Any],
                                     agreement_count: int,
                                     present_count: int) -> None:
        """Handle majority agreement or conflict cases."""
        unique_vals = comparison["unique_values"]
        
        # Find the most common value
        most_common_key = max(unique_vals.keys(), 
                            key=lambda k: len(unique_vals[k]))
        most_common_models = unique_vals[most_common_key]
        
        # Extract actual value
        model_with_value = most_common_models[0]
        value = comparison["values"][model_with_value]
        
        # Calculate confidence
        confidence = len(most_common_models) / present_count
        
        # Classify as majority (2/3) or conflicting (1/3 each)
        if len(most_common_models) >= 2:
            self.comparison_results["majority_fields"][field_name] = {
                "value": value,
                "agreement_models": most_common_models,
                "conflict_models": [m for m in comparison["present_in"] 
                                   if m not in most_common_models],
            }
        else:
            self.comparison_results["conflicting_fields"][field_name] = {
                "value1": {comparison["present_in"][0]: comparison["values"][comparison["present_in"][0]]},
                "value2": {comparison["present_in"][1]: comparison["values"][comparison["present_in"][1]]},
                "value3": {comparison["present_in"][2]: comparison["values"][comparison["present_in"][2]]} 
                         if len(comparison["present_in"]) > 2 else None,
            }
        
        self.comparison_results["confidence_scores"][field_name] = confidence
    
    def _handle_missing_field(self, field_name: str, 
                            comparison: Dict[str, Any]) -> None:
        """Handle fields missing in some outputs."""
        self.comparison_results["missing_fields"][field_name] = {
            "present_in": comparison["present_in"],
            "missing_from": comparison["missing_from"],
            "values": comparison["values"],
        }
        
        # Confidence is lower for missing fields
        total = max(1, len(comparison["present_in"]) + len(comparison["missing_from"]))
        confidence = len(comparison["present_in"]) / total
        self.comparison_results["confidence_scores"][field_name] = confidence
    
    def get_recommended_value(self, field_name: str) -> Tuple[Any, float]:
        """
        Get recommended value for a field based on comparisons.
        
        Priority order:
        1. Unanimous agreement (confidence 1.0)
        2. Majority agreement (confidence 2/3)
        3. First available value (confidence < 2/3)
        
        Args:
            field_name: Field name
        
        Returns:
            Tuple of (recommended_value, confidence_score)
        """
        confidence = self.comparison_results["confidence_scores"].get(
            field_name, 0.0
        )
        
        # Check unanimous
        if field_name in self.comparison_results["unanimous_fields"]:
            value = self.comparison_results["unanimous_fields"][field_name]
            return value, 1.0
        
        # Check majority
        if field_name in self.comparison_results["majority_fields"]:
            value = self.comparison_results["majority_fields"][field_name]["value"]
            return value, confidence
        
        # Check conflicting
        if field_name in self.comparison_results["conflicting_fields"]:
            conflict = self.comparison_results["conflicting_fields"][field_name]
            # Return first available value
            for key in ["value1", "value2", "value3"]:
                if conflict.get(key):
                    value = list(conflict[key].values())[0]
                    return value, confidence
        
        # Check missing
        if field_name in self.comparison_results["missing_fields"]:
            missing = self.comparison_results["missing_fields"][field_name]
            values = missing["values"]
            if values:
                # Return first available value
                return next(iter(values.values())), confidence
        
        return None, 0.0
    
    def generate_comparison_report(self) -> str:
        """Generate human-readable comparison report."""
        report = []
        report.append("=== FIELD COMPARISON REPORT ===\n")
        
        # Unanimous
        report.append(f"UNANIMOUS AGREEMENT ({len(self.comparison_results['unanimous_fields'])} fields):")
        for field_name in sorted(self.comparison_results["unanimous_fields"].keys())[:10]:
            report.append(f"  ✓ {field_name}")
        if len(self.comparison_results["unanimous_fields"]) > 10:
            report.append(f"  ... and {len(self.comparison_results['unanimous_fields']) - 10} more")
        
        # Majority
        report.append(f"\nMAJORITY AGREEMENT ({len(self.comparison_results['majority_fields'])} fields):")
        for field_name, data in sorted(self.comparison_results["majority_fields"].items())[:5]:
            agreement_models = ", ".join(data["agreement_models"])
            report.append(f"  ⚠ {field_name}: {agreement_models} agree")
        
        # Conflicts
        report.append(f"\nCONFLICTS ({len(self.comparison_results['conflicting_fields'])} fields):")
        for field_name in list(self.comparison_results["conflicting_fields"].keys())[:5]:
            report.append(f"  ✗ {field_name}")
        
        # Missing
        report.append(f"\nMISSING ({len(self.comparison_results['missing_fields'])} fields):")
        for field_name, data in sorted(self.comparison_results["missing_fields"].items())[:5]:
            missing_from = ", ".join(data["missing_from"])
            report.append(f"  ⊘ {field_name}: missing from {missing_from}")
        
        return "\n".join(report)
