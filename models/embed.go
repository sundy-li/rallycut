// Package models exposes the pinned model manifest to the first-run installer.
package models

import _ "embed"

// Manifest is the checked-in record of model sources, hashes and licenses.
//
//go:embed manifest.json
var Manifest []byte
