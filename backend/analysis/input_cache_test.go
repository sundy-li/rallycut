package analysis

import "testing"

func TestCacheKeyIsStableAndSourceSpecific(t *testing.T) {
	if CacheKey("a") != CacheKey("a") || CacheKey("a") == CacheKey("b") {
		t.Fatal("cache key must be stable and per-source")
	}
}
