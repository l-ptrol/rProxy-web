package core

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Load загружает конфигурационный файл формата Bash (KEY='VALUE')
// и возвращает карту ключ-значение.
func LoadConfig(filePath string) map[string]string {
	config := make(map[string]string)

	file, err := os.Open(filePath)
	if err != nil {
		return config
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Пропускаем пустые строки и комментарии
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		// Разбиваем по первому '='
		idx := strings.Index(line, "=")
		if idx < 0 {
			continue
		}

		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])

		// Убираем кавычки вокруг значения
		val = strings.Trim(val, "'")
		val = strings.Trim(val, "\"")

		config[key] = val
	}

	return config
}

// SaveConfig сохраняет конфигурацию в файл в формате Bash (KEY='VALUE')
func SaveConfig(filePath string, data map[string]string) error {
	// Создаём родительскую директорию если не существует
	dir := filepath.Dir(filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("не удалось создать директорию %s: %w", dir, err)
	}

	file, err := os.Create(filePath)
	if err != nil {
		return fmt.Errorf("не удалось создать файл %s: %w", filePath, err)
	}
	defer file.Close()

	writer := bufio.NewWriter(file)
	for key, val := range data {
		// Сохраняем значения в одинарных кавычках для совместимости с Bash
		fmt.Fprintf(writer, "%s='%s'\n", key, val)
	}
	return writer.Flush()
}

// DeleteConfig удаляет файл конфигурации
func DeleteConfig(filePath string) error {
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		return nil
	}
	return os.Remove(filePath)
}
