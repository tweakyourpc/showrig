# Privacy

Wordsmith Studio is a local-first browser application.

- **Account:** No account is required.
- **Text:** The shipped application has no backend request for project text.
  Phrases are processed in the browser.
- **Fonts and images:** Bundled fonts and user-selected images are consumed by
  the browser. The shipped runtime contains no upload path for them.
- **Exports:** GIF encoding occurs in the browser. Video export uses browser
  encoding APIs and produces the download locally.
- **Analytics and telemetry:** The shipped application contains no analytics,
  telemetry, or account system.
- **Offline use:** After the application and its local assets have loaded, the
  editing workflow and GIF export have been verified to work without a network
  connection. This does not promise every browser's video encoder or every
  first-load scenario works offline.
- **Export support:** Video formats depend on browser WebCodecs and supported
  codec and container combinations. GIF export has separate memory and runtime
  limits. The browser reports unsupported formats.

The project does not make a broader claim that every browser, codec, or export
format is supported. If the application is embedded or modified by a host,
that host may add its own services and policies outside this repository.
