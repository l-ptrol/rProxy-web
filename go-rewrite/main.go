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
	// Определяем режим работы
	if len(os.Args) < 2 {
		// Без аргументов — запуск CLI
		runCLI()
		return
	}

	switch os.Args[1] {
	case "web":
		// Запуск веб-сервера (файл встроен внутрь бинарника)
		cmd.StartWebServer(3000, indexHTML)

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
		fmt.Printf("rProxy v%s — Менеджер обратных туннелей\n\n", core.VERSION)
		fmt.Println("Использование:")
		fmt.Println("  rproxy          — Интерактивное CLI-меню")
		fmt.Println("  rproxy web      — Запуск веб-интерфейса (порт 3000)")
		fmt.Println("  rproxy boot     — Автозапуск всех включенных сервисов")
		fmt.Println("  rproxy stop     — Остановка всех сервисов")
		fmt.Println("  rproxy restart  — Перезапуск всех сервисов")
		fmt.Println("  rproxy version  — Показать версию")
	}
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

// runCLI запускает интерактивное CLI-меню
func runCLI() {
	// CLI будет реализовано в cmd/cli.go
	// Пока выводим базовое меню
	for {
		clearScreen()
		core.Header(fmt.Sprintf("rProxy v%s — Go Edition", core.VERSION))

		// Статистика
		total, online, vpsCount := getStats()
		fmt.Printf("  %sСерверов VPS:%s %s%d%s  %sСервисов:%s %s%d%s  %sОнлайн:%s %s%s%d%s\n",
			core.DIM, core.NC, core.BOLD, vpsCount, core.NC,
			core.DIM, core.NC, core.BOLD, total, core.NC,
			core.DIM, core.NC, core.GREEN, core.BOLD, online, core.NC)
		core.DrawSeparator()

		fmt.Printf("  %s1)%s  📋  Список сервисов и статус\n", core.BOLD, core.NC)
		fmt.Printf("  %s2)%s  ➕  Добавить сервис\n", core.BOLD, core.NC)
		fmt.Printf("  %s3)%s  📝  Редактировать сервис\n", core.BOLD, core.NC)
		fmt.Printf("  %s4)%s  ❌  Удалить сервис\n", core.BOLD, core.NC)
		core.DrawSeparator()
		fmt.Printf("  %s5)%s  ▶️   Запустить туннель\n", core.BOLD, core.NC)
		fmt.Printf("  %s6)%s  ⏹️   Остановить туннель\n", core.BOLD, core.NC)
		fmt.Printf("  %s7)%s  🔄  Перезапустить туннель\n", core.BOLD, core.NC)
		core.DrawSeparator()
		fmt.Printf("  %s8)%s  🔒  Управление SSL\n", core.BOLD, core.NC)
		fmt.Printf("  %s9)%s  ⚙️   Настройки VPS\n", core.BOLD, core.NC)
		core.DrawSeparator()
		fmt.Printf("  %s10)%s 🚀  Обновить rProxy\n", core.BOLD, core.NC)
		fmt.Printf("  %s11)%s 🏥  Проверка VPS (Health)\n", core.BOLD, core.NC)
		fmt.Printf("  %s99)%s ☢️   Глубокая очистка\n", core.BOLD, core.NC)
		fmt.Printf("  %s0)%s      Выход\n", core.BOLD, core.NC)

		var choice string
		fmt.Printf("\n%sВыберите действие:%s ", core.BOLD, core.NC)
		fmt.Scanln(&choice)

		switch choice {
		case "1":
			showStatus()
		case "10":
			core.SelfUpdate(false)
		case "99":
			core.HardReset()
		case "0":
			return
		default:
			core.Warn("Функция будет реализована в следующих версиях Go-порта.")
		}

		if choice != "0" {
			core.Pause()
		}
	}
}

func clearScreen() {
	fmt.Print("\033[H\033[2J")
}

func getStats() (total, online, vpsCount int) {
	if entries, err := os.ReadDir(core.ServicesDir); err == nil {
		for _, e := range entries {
			if strings.HasSuffix(e.Name(), ".conf") {
				total++
				name := strings.TrimSuffix(e.Name(), ".conf")
				if core.IsRunning(name) {
					online++
				}
			}
		}
	}
	if entries, err := os.ReadDir(core.VPSDir); err == nil {
		for _, e := range entries {
			if strings.HasSuffix(e.Name(), ".conf") {
				vpsCount++
			}
		}
	}
	return
}

func showStatus() {
	clearScreen()
	core.Header("Список сервисов")

	entries, err := os.ReadDir(core.ServicesDir)
	if err != nil {
		fmt.Printf("\n  %sНет добавленных сервисов.%s\n", core.YELLOW, core.NC)
		return
	}

	var files []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".conf") {
			files = append(files, e.Name())
		}
	}

	if len(files) == 0 {
		fmt.Printf("\n  %sНет добавленных сервисов.%s\n", core.YELLOW, core.NC)
		return
	}

	fmt.Printf("  %s%-4s %-14s %-22s %-7s %-9s %s%s\n",
		core.BOLD, "№", "ИМЯ", "ЦЕЛЬ", "ПОРТ", "СТАТУС", "ДОМЕН", core.NC)
	core.DrawSeparator()

	for idx, f := range files {
		name := strings.TrimSuffix(f, ".conf")
		cfg := core.LoadConfig(filepath.Join(core.ServicesDir, f))
		isOn := core.IsRunning(name)

		status := fmt.Sprintf("%s○ офлайн%s", core.RED, core.NC)
		if isOn {
			status = fmt.Sprintf("%s● онлайн%s", core.GREEN, core.NC)
		}

		targetHost := cfg["SVC_TARGET_HOST"]
		if targetHost == "" {
			targetHost = "127.0.0.1"
		}
		target := fmt.Sprintf("%s:%s", targetHost, cfg["SVC_TARGET_PORT"])
		domain := cfg["SVC_DOMAIN"]
		if domain == "" {
			domain = "---"
		}
		port := cfg["SVC_EXT_PORT"]
		if port == "" {
			port = "---"
		}

		fmt.Printf("  %-4d %-14s %-22s %-7s %s %s\n", idx+1, name, target, port, status, domain)
	}
}
