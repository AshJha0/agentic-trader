# Position sizing methodology

## Strategic weight and tactical tilt

Every instrument has a strategic (benchmark) weight held when the desk has no directional
view: 1.0 for equities, which carry a long-run risk premium, and 0.0 for currency pairs,
which do not apart from carry. The trader sets the target as the strategic weight plus a
tilt of twice the debate score when the absolute score exceeds the decision threshold of
0.10. Weights are clipped to the range -1 to +1.

## Volatility targeting

The neutral risk analyst scales the trader's target so that the position's expected
annualised volatility equals the 15% target: weight multiplied by target volatility over
the 20-day realised volatility. A more volatile instrument receives a smaller position for
the same conviction. When realised volatility is zero or unavailable the vol-targeted
weight is zero.

## Aggressive and conservative views

The aggressive analyst recommends the larger of 1.25 times the trader's size and the
vol-targeted size. The conservative analyst recommends half of the smaller of the two,
then reduces it further so that the position's one-day 95% VaR stays within the 2% cap.

## Blending

The portfolio manager blends the latest views with weights of 25% aggressive, 50% neutral
and 25% conservative, or takes the language model's proposed weight when one is
available. Firm limits then apply.

## Track record adjustment

When the decision memory shows a hit rate below 40% over at least five resolved calls on
the instrument, the trader cuts the target by 25%. Recent poor calls reduce size; they do
not change direction.
