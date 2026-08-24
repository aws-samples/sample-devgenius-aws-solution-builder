import { useState } from "react"
import { Authenticator } from "@aws-amplify/ui-react"
import "@aws-amplify/ui-react/styles.css"
import TopNavigation from "@cloudscape-design/components/top-navigation"
import { applyMode, Mode } from "@cloudscape-design/global-styles"
import Console from "./Console"

export default function App() {
  return (
    <Authenticator signUpAttributes={["email"]} loginMechanisms={["email"]}>
      {({ signOut, user }) => <Shell email={emailOf(user)} onSignOut={signOut} />}
    </Authenticator>
  )
}

function emailOf(user: unknown): string {
  const u = user as { signInDetails?: { loginId?: string }; username?: string } | undefined
  return u?.signInDetails?.loginId ?? u?.username ?? ""
}

function Shell({ email, onSignOut }: { email: string; onSignOut?: () => void }) {
  const [dark, setDark] = useState(false)

  function toggleTheme() {
    const next = !dark
    setDark(next)
    applyMode(next ? Mode.Dark : Mode.Light)
  }

  return (
    <>
      <div id="top-nav">
        <TopNavigation
          identity={{ href: "#", title: "DevGenius" }}
          utilities={[
            {
              type: "button",
              iconName: dark ? "star-filled" : "star",
              text: dark ? "Light" : "Dark",
              onClick: toggleTheme,
            },
            {
              type: "menu-dropdown",
              text: email || "Account",
              iconName: "user-profile",
              items: [{ id: "signout", text: "Sign out" }],
              onItemClick: ({ detail }) => detail.id === "signout" && onSignOut?.(),
            },
          ]}
        />
      </div>
      <Console email={email} />
    </>
  )
}
