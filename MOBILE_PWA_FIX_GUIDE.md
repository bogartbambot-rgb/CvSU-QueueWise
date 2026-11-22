# QueueWise v1.12.1 — Mobile Install Fix

The public landing page previously hid the Install App header control at widths <=530px. The fix restores it as an icon-only header action and adds an obvious **Install QueueWise App** control beneath the sign-in/create-account actions on narrow screens. The install dialog now explains Android and iPhone installation separately. Apple home-screen metadata and a 180px touch icon are included.

## Update existing GitHub deployment

1. Extract the ZIP. The source folder inside it is `CvSU_QueueWise_PWA`.
2. Copy the updated files into your existing Git repository. **Do not overwrite or commit** your `.env`, `instance/`, SQLite files, or secrets.
3. Run `git add .`, inspect `git status`, then `git commit -m "Fix QueueWise mobile PWA install button v1.12.1"`, `git push origin main`.
4. Verify the latest commit deploys successfully on Railway. Keep the `/data` volume attached.
5. On your phone, open the HTTPS Railway link in **Chrome (Android)** or **Safari (iPhone)** and refresh. The landing page should show an Install button in its hero area. When no native prompt exists, the button opens instructions.

## Phone installation

- Android Chrome: **⋮ > Install app**, or **Add to Home screen** if offered.
- iPhone Safari: **Share > Add to Home Screen > Add** (enable **Open as Web App** when offered).
- In-app browsers like Messenger and Facebook may not expose installation controls; open externally in Chrome/Safari.
- If already installed, open QueueWise from the home screen. A new install prompt may not appear.

**Note:** Clicking the QueueWise Install button cannot force a browser-native popup when the browser doesn't support it; the guidance modal is the fallback. The PWA is not a native offline backend: submitting and tracking requests still needs the server.
