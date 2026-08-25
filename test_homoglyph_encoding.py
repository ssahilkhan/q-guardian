import asyncio
from q_guardian.security.homoglyph import analyze_homoglyphs
from q_guardian.security.encoding import detect_all_encodings

# Test homoglyph detection
cyrillic_a = "\u0430"  # Cyrillic small letter a
result = analyze_homoglyphs(f"he{cyrillic_a}lo")
print("Homoglyph test (Cyrillic a in hello):")
print("  has_confusables:", result["has_confusables"])
print("  has_mixed_script:", result["has_mixed_script"])
print("  confusables:", result["confusables"])

# Test encoding detection
encoded = "SGVsbG8gV29ybGQ="  # base64 'Hello World'
result2 = detect_all_encodings(encoded)
print("Encoding test (base64):")
print("  candidates:", len(result2))
for c in result2:
    print(" ", c.encoding, ":", c.decoded[:30], "... (confidence=", c.confidence, ")")
