package main

import (
	"fmt"
	"os"
	"path/filepath"
	"rproxy/cmd"
	"rproxy/core"
	"strings"
	"sync"
	"time"
	_ "embed"
)

//go:embed templates/index.html
var indexHTML []byte

//go:embed templates/login.html
var loginHTML []byte

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
		core.WebPort = port
		// Сохраняем порт в конфиг для туннелей
		gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
		gCfg := core.LoadConfig(gPath)
		gCfg["RPROXY_PORT"] = fmt.Sprintf("%d", port)
		core.SaveConfig(gPath, gCfg)

		// Запуск веб-сервера (файл встроен внутрь бинарника)
		cmd.StartWebServer(port, indexHTML, loginHTML)

	case "boot":
		// Автозагрузка: запуск всех enabled сервисов
		delayOverride := ""
		if len(os.Args) >= 3 {
			delayOverride = os.Args[2]
		}
		bootServices(delayOverride)

	case "stop":
		// Остановка всех сервисов
		stopAllServices()

	case "restart":
		// Перезапуск
		stopAllServices()
		time.Sleep(2 * time.Second)
		bootServices("")

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
func bootServices(delayOverride string) {
	// Загружаем общие настройки для получения задержки
	gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
	gCfg := core.LoadConfig(gPath)

	delaySec := 60
	if delayOverride != "" {
		fmt.Sscanf(delayOverride, "%d", &delaySec)
	} else if val, ok := gCfg["BOOT_DELAY"]; ok {
		fmt.Sscanf(val, "%d", &delaySec)
	}

	if delaySec > 0 {
		core.Msg(fmt.Sprintf("Ожидание %d сек перед запуском туннелей...", delaySec))
		time.Sleep(time.Duration(delaySec) * time.Second)
	}

	core.Msg("Параллельный автозапуск включенных сервисов...")

	entries, err := os.ReadDir(core.ServicesDir)
	if err != nil {
		core.Warn("Нет директории с сервисами.")
		return
	}

	var wg sync.WaitGroup
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".conf") {
			continue
		}

		wg.Add(1)
		go func(entry os.DirEntry) {
			defer wg.Done()
			name := strings.TrimSuffix(entry.Name(), ".conf")
			cfg := core.LoadConfig(filepath.Join(core.ServicesDir, entry.Name()))

			if cfg["SVC_ENABLED"] != "yes" {
				return
			}

			vpsID := cfg["SVC_VPS"]
			if vpsID == "" {
				core.Warn(fmt.Sprintf("Сервис '%s' — VPS не указан.", name))
				return
			}

			vpsPath := filepath.Join(core.VPSDir, vpsID+".conf")
			if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
				core.Warn(fmt.Sprintf("Сервис '%s' — VPS '%s' не найден.", name, vpsID))
				return
			}

			vpsCfg := core.LoadConfig(vpsPath)
			core.Msg(fmt.Sprintf("Запуск '%s'...", name))
			core.StartService(cfg, vpsCfg, false)
		}(e)
	}

	wg.Wait()
	core.Msg("Автозапуск завершён.")
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


