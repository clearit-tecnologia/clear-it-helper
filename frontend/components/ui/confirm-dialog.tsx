"use client";

import { useId, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Accessible confirmation: focus starts on "Cancelar" (safe default), Esc cancels. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancelar",
  destructive = false,
  isConfirming = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const id = useId();
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      labelledBy={`${id}-title`}
      describedBy={`${id}-description`}
      role="alertdialog"
    >
      <div className="flex flex-col gap-4 p-6">
        <h2 id={`${id}-title`} className="text-lg font-semibold">
          {title}
        </h2>
        <div id={`${id}-description`} className="text-sm text-muted-foreground">
          {description}
        </div>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel} data-autofocus disabled={isConfirming}>
            {cancelLabel}
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm} disabled={isConfirming}>
            {isConfirming ? "Aguarde…" : confirmLabel}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
