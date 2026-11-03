# Selected services on Home

Windows 0.25.1 → 0.25.2, synchronized across React/native/installer manifests.
Android 0.21.1/code40 → 0.21.2/code41. Backend 0.32.0 and website 0.2.2 unchanged.
This is the owner's separate small Home presentation task, after the FAQ task.

In both include and exclude modes, the label and compact icon strip precede the
choose-services button. Existing original logos are rendered first, followed by
the existing fallback letter badges and generic globe icons for custom domains.
Order inside each group is stable. Selection storage is never sorted or mutated.
The row stays single-line and displays an ellipsis only for actual width overflow;
its accessible name/tooltip lists the hidden services. All mode remains unchanged.

Existing Windows component tests cover narrow/wide row capacity, fallback icons,
original-first order even when stored order differs, DOM order and unchanged
selection. Native Windows review checks actual icon/button positions and captures
the resulting Home. Android instrumented acceptance checks real bounds, custom
icons and overflow in both modes. No backend/API, payment or VPN routing changes.

The same delivery also fixes the FAQ task's native Windows finding: the longer
answer exceeded the fixed window. The FAQ card now bounds its answer and allows
keyboard/mouse scrolling inside it; changing a question resets answer scroll.
Native capture covers the beginning and end without relaxing canvas checks.

Final product SHA, current-head all-event CI audit, artifact build SHA/run/attempt,
native screenshot evidence and publication status are recorded in PR50 after
checks finish. No new release tags or merge are part of these changes.
