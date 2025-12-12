"""
Unit tests for ga_friendliness feature engineering.
"""

import pytest

from shared.ga_friendliness import (
    FeatureMapper,
    AIRCRAFT_MTOW_MAP,
    get_mtow_for_aircraft,
    get_fee_band_for_mtow,
    aggregate_fees_by_band,
    apply_bayesian_smoothing,
    AirportFeatureScores,
)


@pytest.mark.unit
class TestAircraftMTOW:
    """Tests for aircraft MTOW mapping."""

    def test_known_aircraft(self):
        """Test MTOW for known aircraft types."""
        assert get_mtow_for_aircraft("c172") == 1157
        assert get_mtow_for_aircraft("sr22") == 1633
        assert get_mtow_for_aircraft("pa28") == 1111

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert get_mtow_for_aircraft("C172") == 1157
        assert get_mtow_for_aircraft("SR22") == 1633

    def test_unknown_aircraft(self):
        """Test unknown aircraft returns None."""
        assert get_mtow_for_aircraft("unknown") is None
        assert get_mtow_for_aircraft("xyz123") is None


@pytest.mark.unit
class TestFeeBands:
    """Tests for fee band mapping."""

    def test_fee_band_boundaries(self):
        """Test fee band boundary conditions."""
        assert get_fee_band_for_mtow(700) == "fee_band_0_749kg"
        assert get_fee_band_for_mtow(749) == "fee_band_0_749kg"
        assert get_fee_band_for_mtow(750) == "fee_band_750_1199kg"
        assert get_fee_band_for_mtow(1199) == "fee_band_750_1199kg"
        assert get_fee_band_for_mtow(1200) == "fee_band_1200_1499kg"
        assert get_fee_band_for_mtow(1500) == "fee_band_1500_1999kg"
        assert get_fee_band_for_mtow(2000) == "fee_band_2000_3999kg"
        assert get_fee_band_for_mtow(4000) == "fee_band_4000_plus_kg"
        assert get_fee_band_for_mtow(10000) == "fee_band_4000_plus_kg"

    def test_aggregate_fees(self):
        """Test fee aggregation from source data."""
        fee_data = {
            "c172": {"landing": 15.0},
            "sr22": {"landing": 25.0},
            "pa28": 12.0,  # Direct value
        }
        
        result = aggregate_fees_by_band(fee_data)
        
        # c172 (1157kg) and pa28 (1111kg) both in 750-1199 band
        assert result["fee_band_750_1199kg"] is not None
        assert abs(result["fee_band_750_1199kg"] - 13.5) < 0.01  # Average of 15 and 12
        
        # sr22 (1633kg) in 1500-1999 band
        assert result["fee_band_1500_1999kg"] == 25.0
        
        # Other bands should be None
        assert result["fee_band_0_749kg"] is None

    def test_aggregate_fees_empty(self):
        """Test fee aggregation with empty data."""
        result = aggregate_fees_by_band({})
        assert all(v is None for v in result.values())


@pytest.mark.unit
class TestFeatureMapper:
    """Tests for FeatureMapper class."""

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_map_cost_score(self):
        """Test cost score mapping."""
        mapper = FeatureMapper()

        # All cheap
        cheap_dist = {"cheap": 5.0}
        assert mapper.map_cost_score(cheap_dist) == 1.0
        
        # All expensive
        expensive_dist = {"expensive": 5.0}
        assert mapper.map_cost_score(expensive_dist) == 0.2
        
        # Mixed
        mixed_dist = {"cheap": 1.0, "expensive": 1.0}
        score = mapper.map_cost_score(mixed_dist)
        assert 0.4 <= score <= 0.8  # Should be between the two

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_map_hassle_score(self):
        """Test hassle score mapping."""
        mapper = FeatureMapper()
        
        # Simple bureaucracy
        simple_dist = {"simple": 5.0}
        score = mapper.map_hassle_score(simple_dist)
        assert score == 1.0
        
        # Complex bureaucracy
        complex_dist = {"complex": 5.0}
        score = mapper.map_hassle_score(complex_dist)
        assert score == 0.2

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_map_hassle_with_notification(self):
        """Test hassle score with AIP notification score."""
        mapper = FeatureMapper()
        
        # Review says simple, AIP says complex (low notification_score)
        dist = {"simple": 5.0}  # Would be 1.0 alone
        notification_score = 0.2  # High hassle from AIP
        
        score = mapper.map_hassle_score(dist, notification_score)
        # 0.7 * 1.0 + 0.3 * 0.2 = 0.76
        assert 0.7 <= score <= 0.8

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_map_hospitality_score(self):
        """Test hospitality score mapping."""
        mapper = FeatureMapper()
        
        restaurant_dist = {"on_site": 5.0}
        accommodation_dist = {"walking": 5.0}
        
        score = mapper.map_hospitality_score(restaurant_dist, accommodation_dist)
        # 0.6 * 1.0 + 0.4 * 0.8 = 0.92
        assert 0.9 <= score <= 0.95

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_map_ops_ifr_score_no_procedures(self):
        """Test IFR score when no procedures available."""
        mapper = FeatureMapper()
        
        score = mapper.map_ops_ifr_score(ifr_procedure_available=False)
        assert score == 0.1  # Very low

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_map_ops_ifr_score_with_procedures(self):
        """Test IFR score when procedures available."""
        mapper = FeatureMapper()
        
        score = mapper.map_ops_ifr_score(ifr_procedure_available=True)
        assert score >= 0.7  # Good score

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_compute_feature_scores(self):
        """Test computing all feature scores."""
        mapper = FeatureMapper()
        
        distributions = {
            "cost": {"cheap": 3.0, "reasonable": 2.0},
            "bureaucracy": {"simple": 4.0, "moderate": 1.0},
            "overall_experience": {"positive": 5.0},
            "restaurant": {"on_site": 3.0},
            "accommodation": {"nearby": 2.0},
            "transport": {"good": 4.0},
            "runway": {"excellent": 3.0},
        }
        
        scores = mapper.compute_feature_scores(
            icao="EGKB",
            distributions=distributions,
            ifr_procedure_available=True,
        )
        
        assert scores.icao == "EGKB"
        assert 0.0 <= scores.ga_cost_score <= 1.0
        assert 0.0 <= scores.ga_review_score <= 1.0
        assert 0.0 <= scores.ga_hassle_score <= 1.0
        assert 0.0 <= scores.ga_ops_ifr_score <= 1.0
        assert 0.0 <= scores.ga_hospitality_score <= 1.0

    @pytest.mark.skip(reason="FeatureMapper API refactored - tests need to be rewritten for config-driven approach")
    def test_empty_distributions(self):
        """Test with empty distributions."""
        mapper = FeatureMapper()
        
        scores = mapper.compute_feature_scores(
            icao="EGKB",
            distributions={},
            ifr_procedure_available=False,
        )
        
        # All scores should be defaults (0.5 or similar)
        assert scores.ga_cost_score == 0.5
        assert scores.ga_review_score == 0.5


@pytest.mark.unit
class TestBayesianSmoothing:
    """Tests for Bayesian smoothing."""

    def test_no_samples(self):
        """Test with no samples returns prior."""
        result = apply_bayesian_smoothing(
            score=0.8,
            sample_count=0,
            prior=0.5,
        )
        assert result == 0.5

    def test_many_samples(self):
        """Test with many samples approaches raw score."""
        result = apply_bayesian_smoothing(
            score=0.9,
            sample_count=100,
            prior=0.5,
            strength=10.0,
        )
        # (10 * 0.5 + 100 * 0.9) / 110 = 95 / 110 ≈ 0.864
        assert 0.85 <= result <= 0.9

    def test_few_samples(self):
        """Test with few samples pulls toward prior."""
        result = apply_bayesian_smoothing(
            score=0.9,
            sample_count=2,
            prior=0.5,
            strength=10.0,
        )
        # (10 * 0.5 + 2 * 0.9) / 12 = 6.8 / 12 ≈ 0.567
        assert 0.5 <= result <= 0.65  # Should be much closer to prior

    def test_smoothing_strength(self):
        """Test that higher strength means more smoothing."""
        weak = apply_bayesian_smoothing(
            score=0.9,
            sample_count=5,
            prior=0.5,
            strength=5.0,
        )
        strong = apply_bayesian_smoothing(
            score=0.9,
            sample_count=5,
            prior=0.5,
            strength=20.0,
        )
        
        # Strong smoothing should be closer to prior (0.5)
        assert abs(strong - 0.5) < abs(weak - 0.5)

