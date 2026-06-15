"""
SMARTER Engine — Core multicriteria decision analysis module.

Implements the SMARTER method (Edwards & Barron, 1994) with:
- ROC (Rank Order Centroid) weight calculation
- Interval scale normalization using historical min/max
- Global value computation V(a, t) across all historical periods
"""

import logging
from datetime import date
from typing import Optional

from sqlalchemy import func

from models import db
from models.indicator_history import IndicatorHistory
from models.decision_problem import DecisionProblem, DecisionCriteria, DecisionAlternative
from models.recommendation import GlobalValue

logger = logging.getLogger(__name__)


class SMARTEREngine:
    """Core SMARTER multicriteria decision analysis engine."""

    # ─── ROC Weight Calculation ──────────────────────────────────────────

    @staticmethod
    def calculate_roc_weights(n: int) -> list[float]:
        """
        Calculate Rank Order Centroid (ROC) weights for N ranked criteria.

        Formula: w_i = (1/N) * Σ(1/j) for j = i to N

        Args:
            n: Number of criteria

        Returns:
            List of weights (sum = 1.0), ordered from rank 1 to N
        """
        if n <= 0:
            return []

        weights = []
        for i in range(1, n + 1):
            w_i = (1.0 / n) * sum(1.0 / j for j in range(i, n + 1))
            weights.append(w_i)

        return weights

    # ─── Normalization ───────────────────────────────────────────────────

    @staticmethod
    def normalize_value(value: float, min_hist: float, max_hist: float,
                        is_cost: bool) -> float:
        """
        Normalize a raw indicator value to [0, 1] using interval scale.

        For benefit criteria: v = (x - min) / (max - min)
        For cost criteria:    v = (max - x) / (max - min)

        Uses historical global min/max across ALL companies and ALL periods.

        Args:
            value: Raw indicator value
            min_hist: Historical minimum across all companies/periods
            max_hist: Historical maximum across all companies/periods
            is_cost: True if lower is better

        Returns:
            Normalized value in [0, 1]
        """
        if max_hist == min_hist:
            return 0.5  # Degenerate case: all values are the same

        if is_cost:
            normalized = (max_hist - value) / (max_hist - min_hist)
        else:
            normalized = (value - min_hist) / (max_hist - min_hist)

        # Clamp to [0, 1] to handle edge cases
        return max(0.0, min(1.0, normalized))

    # ─── Historical Bounds ───────────────────────────────────────────────

    @staticmethod
    def get_historical_bounds(indicator_id: int) -> tuple[Optional[float], Optional[float]]:
        """
        Get the global historical min and max for an indicator across ALL companies
        and ALL periods.

        Args:
            indicator_id: ID of the indicator definition

        Returns:
            Tuple of (min_value, max_value), or (None, None) if no data
        """
        result = db.session.query(
            func.min(IndicatorHistory.value),
            func.max(IndicatorHistory.value)
        ).filter(
            IndicatorHistory.indicator_id == indicator_id,
            IndicatorHistory.value.isnot(None)
        ).first()

        if result and result[0] is not None:
            return result[0], result[1]
        return None, None

    # ─── Available Periods ───────────────────────────────────────────────

    @staticmethod
    def get_available_periods(company_ids: list[int]) -> list[date]:
        """
        Get all unique period dates that have indicator data for any of the
        given companies.

        Args:
            company_ids: List of company IDs

        Returns:
            Sorted list of dates
        """
        dates = db.session.query(
            IndicatorHistory.period_date
        ).filter(
            IndicatorHistory.company_id.in_(company_ids),
            IndicatorHistory.value.isnot(None)
        ).distinct().order_by(
            IndicatorHistory.period_date
        ).all()

        return [d[0] for d in dates]

    # ─── Global Value Calculation ────────────────────────────────────────

    def calculate_global_value(
        self,
        company_id: int,
        period_date: date,
        criteria: list[DecisionCriteria],
        bounds_cache: dict
    ) -> Optional[tuple[float, dict]]:
        """
        Calculate the SMARTER global value V(a, t) for one company at one period.

        Steps:
        1. Fetch indicator values for this company/period
        2. Filter to criteria with available data
        3. Recalculate ROC weights for available criteria
        4. Normalize each value using historical bounds
        5. Compute weighted sum

        Args:
            company_id: Company ID
            period_date: Date of the period
            criteria: List of DecisionCriteria objects (ordered by rank)
            bounds_cache: Dict of {indicator_id: (min, max)} for performance

        Returns:
            Tuple of (global_value, {indicator_code: normalized_value}) or None
        """
        # 1. Fetch all indicator values for this company on or near this date
        indicator_values = {}
        for criterion in criteria:
            value_record = IndicatorHistory.query.filter(
                IndicatorHistory.company_id == company_id,
                IndicatorHistory.indicator_id == criterion.indicator_id,
                IndicatorHistory.period_date == period_date,
                IndicatorHistory.value.isnot(None)
            ).first()

            if value_record:
                indicator_values[criterion.indicator_id] = value_record.value

        # 2. Filter criteria with available data
        available_criteria = [c for c in criteria if c.indicator_id in indicator_values]

        if not available_criteria:
            return None

        # 3. Recalculate ROC weights for available criteria count
        n = len(available_criteria)
        weights = self.calculate_roc_weights(n)

        # 4. Normalize and compute global value
        global_value = 0.0
        normalized_values = {}

        for i, criterion in enumerate(available_criteria):
            raw_value = indicator_values[criterion.indicator_id]
            indicator_code = criterion.indicator.code if criterion.indicator else str(criterion.indicator_id)

            # Get bounds from cache
            bounds = bounds_cache.get(criterion.indicator_id)
            if bounds is None or bounds[0] is None:
                continue

            min_hist, max_hist = bounds
            is_cost = criterion.criteria_type == 'cost'

            normalized = self.normalize_value(raw_value, min_hist, max_hist, is_cost)
            normalized_values[indicator_code] = round(normalized, 6)

            global_value += weights[i] * normalized

        return global_value, normalized_values

    # ─── Full Calculation Pipeline ───────────────────────────────────────

    def run_full_calculation(self, problem_id: int) -> dict:
        """
        Run the complete SMARTER calculation for a decision problem:
        compute V(a, t) for ALL companies × ALL periods.

        Args:
            problem_id: Decision problem ID

        Returns:
            Summary dict with counts and status
        """
        problem = DecisionProblem.query.get(problem_id)
        if not problem:
            raise ValueError(f"Decision problem {problem_id} not found")

        # Get criteria ordered by rank
        criteria = DecisionCriteria.query.filter_by(
            problem_id=problem_id
        ).order_by(DecisionCriteria.rank_position).all()

        if not criteria:
            raise ValueError("No criteria defined for this problem")

        # Calculate ROC weights and store them
        n = len(criteria)
        roc_weights = self.calculate_roc_weights(n)
        for i, criterion in enumerate(criteria):
            criterion.roc_weight = roc_weights[i]
        db.session.flush()

        # Get alternatives (companies)
        alternatives = DecisionAlternative.query.filter_by(
            problem_id=problem_id
        ).all()
        company_ids = [a.company_id for a in alternatives]

        if not company_ids:
            raise ValueError("No alternatives selected for this problem")

        # Pre-cache historical bounds for all indicators
        bounds_cache = {}
        for criterion in criteria:
            bounds_cache[criterion.indicator_id] = self.get_historical_bounds(criterion.indicator_id)

        # Get all available periods
        all_periods = self.get_available_periods(company_ids)
        logger.info(f"Calculating V(a,t) for {len(company_ids)} companies × {len(all_periods)} periods")

        # Clear existing results for this problem
        GlobalValue.query.filter_by(problem_id=problem_id).delete()
        db.session.flush()

        # Calculate global values
        total_calculated = 0
        for company_id in company_ids:
            for period in all_periods:
                result = self.calculate_global_value(
                    company_id, period, criteria, bounds_cache
                )
                if result is not None:
                    gv, norm_vals = result
                    global_val = GlobalValue(
                        problem_id=problem_id,
                        company_id=company_id,
                        period_date=period,
                        global_value=gv,
                    )
                    global_val.normalized_values = norm_vals
                    db.session.add(global_val)
                    total_calculated += 1

        db.session.commit()
        logger.info(f"Calculated {total_calculated} global values for problem {problem_id}")

        return {
            'problem_id': problem_id,
            'companies': len(company_ids),
            'periods': len(all_periods),
            'total_calculated': total_calculated,
            'criteria_weights': {c.indicator.code: c.roc_weight for c in criteria},
        }
