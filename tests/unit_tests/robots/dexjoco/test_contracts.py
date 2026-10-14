# Copyright 2026 The HEART Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression checks against the actual frozen evaluator, not copied examples."""


import numpy as np
import pytest

from robots.dexjoco.contracts import (
    environment_action,
    public_observation,
    validate_vector,
)


@pytest.mark.parametrize("bad", [True, "1", float("nan"), float("inf")])
def test_bad_row_fails_before_conversion(bad):
    row = [0.0] * 22
    row[7] = bad
    with pytest.raises(ValueError):
        validate_vector({"vector": row}, False)
