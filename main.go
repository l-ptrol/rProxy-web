package main

import (
	"fmt"
	"os"
	"path/filepath"
	"rproxy/cmd"
	"rproxy/core"
	"strings"
	"time"
	_ "embed"
)

//go:embed templates/index.html
var indexHTML []byte

func main() {

	if len(os.Args) < 2 {
		printHelp()
		return
	}

	switch os.Args[1] {
	case "web":
		port := 3000
		if len(os.Args) >= 3 {
			fmt.Sscanf(os.Args[2], "%d", &port)
		}
		// Запуск веб-сервера (файл встроен внутрь бинарника)
		cmd.StartWebServer(port, indexHTML)

	case "boot":
		// Автозагрузка: запуск всех enabled сервисов
		bootServices()

	case "stop":
		// Остановка всех сервисов
		stopAllServices()

	case "restart":
		// Перезапуск
		stopAllServices()
		time.Sleep(2 * time.Second)
		bootServices()

	case "version", "-v", "--version":
		fmt.Printf("rProxy v%s (Go)\n", core.VERSION)

	default:
		printHelp()
	}
}

func printHelp() {
	fmt.Printf("rProxy v%s — Менеджер обратных туннелей\n\n", core.VERSION)
	fmt.Println("Использование:")
	fmt.Println("  rproxy web [port] — Запуск веб-интерфейса (по умолчанию 3000)")
	fmt.Println("  rproxy boot       — Автозапуск всех включенных сервисов")
	fmt.Println("  rproxy stop       — Остановка всех сервисов")
	fmt.Println("  rproxy restart    — Перезапуск всех сервисов")
	fmt.Println("  rproxy version    — Показать версию")
}

// bootServices запускает все сервисы с SVC_ENABLED=yes
func bootServices() {
	core.Msg("Автозапуск включенных сервисов...")

	entries, err := os.ReadDir(core.ServicesDir)
	if err != nil {
		core.Warn("Нет директории с сервисами.")
		return
	}

	started := 0
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".conf") {
			continue
		}

		name := strings.TrimSuffix(e.Name(), ".conf")
		cfg := core.LoadConfig(filepath.Join(core.ServicesDir, e.Name()))

		if cfg["SVC_ENABLED"] != "yes" {
			continue
		}

		vpsID := cfg["SVC_VPS"]
		if vpsID == "" {
			core.Warn(fmt.Sprintf("Сервис '%s' — VPS не указан, пропускаю.", name))
			continue
		}

		vpsPath := filepath.Join(core.VPSDir, vpsID+".conf")
		if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
			core.Warn(fmt.Sprintf("Сервис '%s' — VPS '%s' не найден, пропускаю.", name, vpsID))
			continue
		}

		vpsCfg := core.LoadConfig(vpsPath)
		core.Msg(fmt.Sprintf("Запуск '%s'...", name))
		if core.StartService(cfg, vpsCfg) {
			started++
		}
	}

	core.Msg(fmt.Sprintf("Автозапуск завершён: %d сервисов запущено.", started))
}

// stopAllServices останавливает все сервисы
func stopAllServices() {
	core.Msg("Остановка всех сервисов...")

	entries, err := os.ReadDir(core.ServicesDir)
	if err != nil {
		return
	}

	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".conf") {
			name := strings.TrimSuffix(e.Name(), ".conf")
			cfg := core.LoadConfig(filepath.Join(core.ServicesDir, e.Name()))
			core.StopService(name, cfg)
		}
	}

	core.Msg("Все сервисы остановлены.")
}


