#!/bin/bash
# Скрипт сборки rProxy Go под три архитектуры роутеров
# Использование: ./build.sh

set -e

VERSION="1.3.9-go"
OUTPUT_DIR="./dist"

# ВАЖНО: Принудительная фиксация тулчейна Go 1.23.8
# Go 1.24+ содержит lock_spinbit.go с futex, которые несовместимы
# со старыми ядрами Linux (3.4.x) на роутерах Keenetic = SIGSEGV.
export GOTOOLCHAIN=go1.23.8

# Очистка старых сборок
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

echo "🔨 Сборка rProxy v${VERSION} (GOTOOLCHAIN=go1.23.8)..."
echo ""

# mipsel (Little Endian) — основная архитектура Keenetic (KN-1010, KN-1810, KN-2710 и др.)
echo "  [1/3] MIPS Little Endian (mipsle) — Keenetic основные модели..."
GOOS=linux GOARCH=mipsle GOMIPS=softfloat go1.23.8 build -ldflags="-s -w" -o "${OUTPUT_DIR}/rproxy-mipsle" .
echo "        ✅ ${OUTPUT_DIR}/rproxy-mipsle"

# mips (Big Endian) — некоторые старые роутеры
echo "  [2/3] MIPS Big Endian (mips) — старые модели..."
GOOS=linux GOARCH=mips GOMIPS=softfloat go1.23.8 build -ldflags="-s -w" -o "${OUTPUT_DIR}/rproxy-mips" .
echo "        ✅ ${OUTPUT_DIR}/rproxy-mips"

# arm64 (aarch64) — новые мощные роутеры (Keenetic Peak, Ultra и др.)
echo "  [3/3] ARM64 (aarch64) — мощные модели..."
GOOS=linux GOARCH=arm64 go1.23.8 build -ldflags="-s -w" -o "${OUTPUT_DIR}/rproxy-arm64" .
echo "        ✅ ${OUTPUT_DIR}/rproxy-arm64"

echo ""
echo "📦 Все бинарники собраны в ${OUTPUT_DIR}/:"
ls -lh ${OUTPUT_DIR}/rproxy-*
echo ""
echo "✅ Готово! Загрузите нужный файл на роутер и переименуйте в 'rproxy'."
