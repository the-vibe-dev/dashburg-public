import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  (props, ref) => {
    return (
      <input
        ref={ref}
        {...props}
        className={cn(
          "w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground",
          "placeholder:text-muted-foreground/60",
          "focus:outline-none focus:ring-1 focus:ring-primary/50 focus:border-primary/50",
          "transition-colors duration-150",
          props.className,
        )}
      />
    );
  },
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  (props, ref) => {
    return (
      <textarea
        ref={ref}
        {...props}
        className={cn(
          "w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground",
          "placeholder:text-muted-foreground/60 resize-none",
          "focus:outline-none focus:ring-1 focus:ring-primary/50 focus:border-primary/50",
          "transition-colors duration-150",
          props.className,
        )}
      />
    );
  },
);
Textarea.displayName = "Textarea";
