import React from "react"
import ReactDOM from "react-dom/client"
import { Amplify } from "aws-amplify"
import "@cloudscape-design/global-styles/index.css"
import "./styles.css"
import { loadConfig } from "./config"
import App from "./App"
import Bootstrap from "./Bootstrap"

async function start() {
  try {
    const cfg = await loadConfig()
    Amplify.configure({
      Auth: {
        Cognito: {
          userPoolId: cfg.userPoolId,
          userPoolClientId: cfg.userPoolClientId,
        },
      },
    })
    render(<App />)
  } catch (err) {
    render(<Bootstrap error={String(err)} />)
  }
}

function render(node: React.ReactNode) {
  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>{node}</React.StrictMode>
  )
}

start()
