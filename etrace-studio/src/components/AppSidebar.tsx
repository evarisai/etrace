import { Activity } from "lucide-react"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-2 pt-1 pb-0">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="sm" className="cursor-pointer">
              <Activity className="size-3.5 text-primary" />
              <span className="text-xs font-medium">etrace</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent />
    </Sidebar>
  )
}
