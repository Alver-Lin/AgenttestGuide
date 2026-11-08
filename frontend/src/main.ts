import { createApp } from 'vue'
import {
  Button,
  ConfigProvider,
  Dropdown,
  Input,
  Menu,
  Modal,
  Tooltip,
  Tree,
  Upload,
  Select,
  Checkbox,
} from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import './style.css'

createApp(App)
  .use(Button)
  .use(ConfigProvider)
  .use(Dropdown)
  .use(Input)
  .use(Menu)
  .use(Modal)
  .use(Tooltip)
  .use(Tree)
  .use(Upload)
  .use(Select)
  .use(Checkbox)
  .mount('#app')
