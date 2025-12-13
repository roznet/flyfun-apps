# FlyFun Android App

An Android app for the FlyFun aviation assistant, providing airport information, flight planning, and an AI chatbot for aviation queries.

## Features

- **Interactive Map**: View European airports on OpenStreetMap (no API key needed!)
- **Airport Details**: Detailed information including runways, procedures, and AIP data
- **GA Friendliness**: Scores and summaries for General Aviation friendliness
- **AI Assistant**: Chat with an aviation-focused AI for flight planning help
- **Filters**: Filter airports by country, procedures, runway length, and more

## Setup

### Prerequisites

- Android Studio Hedgehog (2023.1.1) or later
- JDK 17
- Android SDK with API 34

### Building

```bash
cd android
./gradlew assembleDebug
```

### Running

Open the project in Android Studio and run on an emulator or device.

**No API keys required!** The app uses OpenStreetMap via osmdroid.

## Architecture

- **Kotlin** with **Jetpack Compose** for UI
- **MVVM** architecture with ViewModels
- **Hilt** for dependency injection
- **Retrofit** for networking
- **osmdroid** for OpenStreetMap display (like Leaflet on web)
- **Kotlinx Serialization** for JSON parsing

## API Endpoints

The app connects to `http://ovh.zhaoqian.me:3001/` for:

- `/airports` - List and filter airports
- `/airports/{icao}` - Airport details
- `/rules/{country}` - Aviation rules
- `/ga/*` - GA friendliness data
- `/aviation-agent/chat/stream` - AI chatbot (SSE)

## Project Structure

```
android/app/src/main/java/me/zhaoqian/flyfun/
├── data/
│   ├── api/           # Retrofit API interfaces
│   ├── models/        # Data classes
│   └── repository/    # Data access layer
├── di/                # Hilt modules
├── ui/
│   ├── map/           # Map screen (osmdroid)
│   ├── airport/       # Airport details
│   ├── chat/          # Chat screen
│   └── theme/         # Material 3 theme
├── viewmodel/         # ViewModels
├── FlyFunApplication.kt
└── MainActivity.kt
```

## License

MIT License
