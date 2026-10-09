"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// Native <dialog> + showModal(): the browser provides the focus trap, Esc to close,
// inert background and the `dialog` role, without adding a new dependency.
// Mark the element that should receive initial focus with `data-autofocus`.

const dialogVariants = cva(
  "bg-card p-0 text-card-foreground shadow-lg backdrop:bg-foreground/40 open:flex open:flex-col",
  {
    variants: {
      variant: {
        /** Centered modal (confirmations). */
        center: "w-11/12 max-w-md rounded-lg border",
        /** Side sheet: full width on small screens (drawer), side panel from `sm`. */
        sheet:
          "fixed inset-y-0 left-auto right-0 m-0 h-full max-h-full w-full max-w-full border-l sm:max-w-md lg:max-w-lg",
      },
    },
    defaultVariants: { variant: "center" },
  },
);

export interface DialogProps
  extends Omit<React.DialogHTMLAttributes<HTMLDialogElement>, "open" | "onClose">,
    VariantProps<typeof dialogVariants> {
  open: boolean;
  /** Called on Esc or when the dialog closes itself. */
  onClose: () => void;
  /** id of the visible title (required for an accessible name). */
  labelledBy: string;
  describedBy?: string;
}

export function Dialog({
  open,
  onClose,
  labelledBy,
  describedBy,
  variant,
  className,
  children,
  ...props
}: DialogProps) {
  const ref = React.useRef<HTMLDialogElement>(null);
  const returnFocusRef = React.useRef<HTMLElement | null>(null);
  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;

  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.hasAttribute("open")) {
      returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      // jsdom (tests) has no showModal(); fall back to the `open` attribute.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      // React's autoFocus does not reach elements of a dialog opened after mount.
      dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    } else if (!open && dialog.hasAttribute("open")) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
    if (!open && returnFocusRef.current) {
      const target = returnFocusRef.current;
      returnFocusRef.current = null;
      if (target.isConnected) target.focus();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      aria-modal="true"
      className={cn(dialogVariants({ variant }), className)}
      onClose={() => {
        if (open) onCloseRef.current();
      }}
      {...props}
    >
      {open ? children : null}
    </dialog>
  );
}
