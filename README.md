# MiniRates

**MiniRates** is a lightweight, modern desktop application built with **Python + Tkinter** for live tracking of exchange rates, gold, and cryptocurrencies.  
It provides a compact and responsive UI with mini bar charts (SparkBars), daily baselines, smooth scrolling, dynamic tooltips, adjustable brightness, and multiple themes.

---

## ✨ Features

- 📊 **Rates list** with smooth scrolling and deltas (change vs. baseline)  
- 🔥 **SparkBar mini charts** showing short-term price changes  
- 📰 **News bar** powered by Twitter/X API  
- 🌙 **Multiple themes** (Dark / Light / Minimal)  
- 📌 **Pin favorite items** to always show at the top  
- ⬆️ **Back-to-top button** for quick navigation  
- 🌟 **Dynamic tooltips** with support for live values  
- 💡 **Brightness / transparency control** via scroll or popup  
- 🖥 **Persistent settings** (size, position, theme, alpha, pins) in JSON  
- 🪟 **System tray integration** with “Show” and “Exit” options  
- ⚡ **Auto-refresh cycle** (default: every 5 minutes)  
- 🛠 **Modular architecture** with clear layers for config, services, UI, and utils  

---

## 📂 Project Structure

```
app/
├─ config/          # Constants, settings, themes
├─ core/            # Events, DI, logging
├─ domain/          # Models and value objects
├─ infra/           # Adapters (e.g., Alanchand)
├─ presentation/    # Mappers and view models
├─ services/        # Data services (cache, catalog, tray, baselines)
├─ ui/              # UI components (window, rows, footer, sparkbar, tooltip, news bar)
└─ utils/           # Utilities (formatting, numbers, net, delta formatting)
```

---

## 🚀 Installation & Run

### Requirements
- Python **3.10+**
- Dependencies listed in `requirements.txt`

### Setup
```bash
git clone https://github.com/imsalione/price-checker.git
cd price-checker
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run
```bash
python -m app.main
```

---

## ⚙️ Settings

Settings are stored in `minirates_settings.json` and include:
- `theme`: active theme (`dark`, `light`, `minimal`)  
- `always_on_top`: window pin state  
- `window_alpha`: transparency (0.5 – 1.0)  
- `pinned_ids`: list of pinned items  
- `news_enabled`: toggle news bar  

---

## 🌐 Data Sources

- [Alanchand](https://alanchand.com/) – scraping exchange, gold, and crypto rates  
- Twitter/X API – live tweets for news updates  

---

## 🛡 Architecture

- **UI Layer**: Modular Tkinter components (`Rows`, `FooterBar`, `NewsBar`, `SparkBar`, `Tooltip`, etc.)  
- **Service Layer**: Cache, baselines, tray service, news fetchers  
- **Config Layer**: Constants, themes, settings manager  
- **Persistence**: JSON-based storage for cache and settings  
- **Events/DI**: Event-driven design with dependency injection support  

---

## 📸 Screenshots

![Main Window](app/assets/screenshots/main-window.png)

---

## 🤝 Contributing

Pull requests and issues are welcome!  
Please run relevant tests before submitting changes.

---

## 📜 License

This project is licensed under the **MIT License**.  
See [LICENSE](LICENSE) for details.
