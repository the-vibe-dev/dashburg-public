import { cn } from "../../lib/utils";

type SelectOption = {
  value: string;
  label: string;
};

type SelectProps = {
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  size?: "sm" | "md";
};

export function Select({
  options,
  value,
  onChange,
  placeholder,
  className,
  size = "md",
}: SelectProps) {
  const sizeClasses = size === "sm"
    ? "px-2 py-1 text-xs"
    : "px-3 py-2 text-sm";

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "appearance-none rounded-lg border border-border bg-input text-foreground",
        "focus:outline-none focus:ring-1 focus:ring-primary/50 focus:border-primary/50",
        "transition-colors duration-150 cursor-pointer",
        "bg-[length:16px_16px] bg-[right_8px_center] bg-no-repeat pr-8",
        "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23888%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')]",
        sizeClasses,
        className,
      )}
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
