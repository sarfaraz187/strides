import { Slider as SliderPrimitive } from "@base-ui/react/slider"

import { cn } from "@/lib/utils"

function Slider({
  className,
  ...props
}: SliderPrimitive.Root.Props<number>) {
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn("relative flex w-full cursor-pointer touch-none items-center select-none", className)}
      {...props}
    >
      <SliderPrimitive.Control className="relative flex w-full items-center py-2">
        <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-border">
          <SliderPrimitive.Indicator className="absolute h-full rounded-full bg-primary" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className="block size-6 rounded-full border-2 border-white bg-primary shadow-[0_1px_4px_rgba(0,0,0,0.3)] outline-none focus-visible:ring-3 focus-visible:ring-primary/40" />
      </SliderPrimitive.Control>
    </SliderPrimitive.Root>
  )
}

export { Slider }
