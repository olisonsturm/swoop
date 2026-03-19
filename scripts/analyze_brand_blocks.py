"""Analyze brand block structure across booking options to find cabin indicators."""

import json
import sys

with open("/tmp/booking_dump_JFK_LHR_business.json") as f:
    raw_options = json.load(f)


def safe_get(data, path, default=None):
    current = data
    for key in path:
        if isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return default
    return current


print("=" * 80)
print("BRAND BLOCK DETAILED COMPARISON")
print("=" * 80)

for i, option in enumerate(raw_options):
    brand_block = safe_get(option, [21])
    brand_code = safe_get(brand_block, [0, 1], "") if brand_block and isinstance(safe_get(brand_block, [0]), list) else ""
    brand_label = safe_get(brand_block, [3], "") if brand_block else ""
    price = safe_get(option, [7, 0, 1], 0)

    print(f"\n--- Option {i}: {brand_label} ({brand_code}) ${price} ---")

    if not brand_block:
        print("  No brand block")
        continue

    for j, val in enumerate(brand_block):
        label = ""
        if j == 0: label = "brand_id"
        elif j == 1: label = "attribute_vector"
        elif j == 2: label = "basic_flag_primary"
        elif j == 3: label = "brand_label"
        elif j == 4: label = "unknown"
        elif j == 16: label = "basic_flag_secondary"

        val_str = json.dumps(val) if val is not None else "null"
        if len(val_str) > 150:
            val_str = val_str[:150] + "..."

        print(f"  [{j:2d}] {label:25s}: {val_str}")


print("\n\n" + "=" * 80)
print("ATTRIBUTE VECTOR COMPARISON")
print("=" * 80)

for i, option in enumerate(raw_options):
    brand_block = safe_get(option, [21])
    brand_code = safe_get(brand_block, [0, 1], "") if brand_block and isinstance(safe_get(brand_block, [0]), list) else ""
    brand_label = safe_get(brand_block, [3], "") if brand_block else ""
    price = safe_get(option, [7, 0, 1], 0)
    attr_vec = safe_get(brand_block, [1]) if brand_block else None

    print(f"\n  Option {i}: {brand_label or '(no brand)'} ({brand_code}) ${price}")
    print(f"    Attribute vector: {json.dumps(attr_vec)}")


print("\n\n" + "=" * 80)
print("FIELD-BY-FIELD DIFF (Option 0 vs Option 1)")
print("=" * 80)

opt0_brand = safe_get(raw_options[0], [21])
opt1_brand = safe_get(raw_options[1], [21])

if opt0_brand and opt1_brand:
    max_len = max(len(opt0_brand), len(opt1_brand))
    for j in range(max_len):
        v0 = opt0_brand[j] if j < len(opt0_brand) else "MISSING"
        v1 = opt1_brand[j] if j < len(opt1_brand) else "MISSING"
        same = "==" if v0 == v1 else "!="
        v0_str = json.dumps(v0) if v0 is not None else "null"
        v1_str = json.dumps(v1) if v1 is not None else "null"
        if len(v0_str) > 80:
            v0_str = v0_str[:80] + "..."
        if len(v1_str) > 80:
            v1_str = v1_str[:80] + "..."
        marker = " *** DIFFERENT ***" if same == "!=" else ""
        print(f"  [{j:2d}] {same} Premium Flex: {v0_str}")
        print(f"       {same} Upper Class:  {v1_str}{marker}")
        print()


print("\n\n" + "=" * 80)
print("BRAND BLOCK [6] FOCUS (suspected cabin indicator)")
print("=" * 80)

for i, option in enumerate(raw_options):
    brand_block = safe_get(option, [21])
    brand_label = safe_get(brand_block, [3], "") if brand_block else ""
    price = safe_get(option, [7, 0, 1], 0)
    field_6 = safe_get(brand_block, [6]) if brand_block else None

    print(f"  Option {i}: {brand_label or '(no brand)'} ${price}")
    print(f"    brand_block[6]: {json.dumps(field_6)}")
    print()
