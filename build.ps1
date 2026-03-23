# Build script for rProxy Go on Windows
$VERSION = "1.9.1-go"
$OUTPUT_DIR = "./dist"

# Set Go toolchain
$env:GOTOOLCHAIN = "go1.23.8"

if (-Not (Test-Path $OUTPUT_DIR)) {
    New-Item -ItemType Directory -Path $OUTPUT_DIR
}

Write-Host "Building rProxy v$VERSION with Go 1.23.8..."

# mipsel
Write-Host "  [1/3] Target: linux/mipsle (softfloat)..."
$env:GOOS = "linux"
$env:GOARCH = "mipsle"
$env:GOMIPS = "softfloat"
go build -ldflags="-s -w" -o "$OUTPUT_DIR/rproxy-mipsle" .

# mips
Write-Host "  [2/3] Target: linux/mips (softfloat)..."
$env:GOOS = "linux"
$env:GOARCH = "mips"
$env:GOMIPS = "softfloat"
go build -ldflags="-s -w" -o "$OUTPUT_DIR/rproxy-mips" .

# arm64
Write-Host "  [3/3] Target: linux/arm64..."
$env:GOOS = "linux"
$env:GOARCH = "arm64"
$env:GOMIPS = ""
go build -ldflags="-s -w" -o "$OUTPUT_DIR/rproxy-arm64" .

Write-Host "Build finished! Binaries are in $OUTPUT_DIR"
