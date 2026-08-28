import javax.swing.*;
import java.awt.*;
import java.awt.event.*;
import java.awt.Point;
import java.util.Random;
import java.util.List;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;
import javax.imageio.ImageIO;
import java.io.IOException;
import java.awt.image.BufferedImage;

public class SnakeGame extends JFrame implements KeyListener {
    // 方向枚举
    private enum Direction {
        UP, RIGHT, DOWN, LEFT
    }

    // 游戏常量
    private static final int GRID_SIZE = 10;          // 网格大小
    private static final int BASE_TIMER_DELAY = 100;  // 基础游戏循环延迟(毫秒)
    private static final int MAX_SNAKE_LENGTH = 200;  // 最大蛇长度 // 已使用于长度限制检查
    private static final String DEFAULT_FONT = "微软雅黑"; // 默认字体
    private static final int GAME_WIDTH = 600;        // 游戏窗口宽度
    private static final int GAME_HEIGHT = 400;       // 游戏窗口高度
    private static final Font GAME_FONT_BOLD_16;      // 游戏字体(粗体16号)
    private static final Font GAME_FONT_BOLD_24;      // 游戏字体(粗体24号)
    private static final Font APPLE_FONT;             // 苹果图标字体

    // 静态初始化字体
    static {
        // 初始化16号粗体字体
        GAME_FONT_BOLD_16 = createFont(DEFAULT_FONT, Font.BOLD, 16);
        // 初始化24号粗体字体
        GAME_FONT_BOLD_24 = createFont(DEFAULT_FONT, Font.BOLD, 24);
        // 初始化苹果图标字体
        APPLE_FONT = createFont("Arial Unicode MS", Font.PLAIN, 12);
    }

    // 字体创建辅助方法
    private static Font createFont(String name, int style, int size) {
        Font font = new Font(name, style, size);
        // 如果字体不存在，使用回退字体
        if (font.getFamily().equals(Font.DIALOG)) {
            return new Font(Font.SANS_SERIF, style, size);
        }
        return font;
    }

    // 游戏状态
    private int currentTimerDelay = BASE_TIMER_DELAY; // 当前游戏速度(初始化为基础延迟)
    private boolean running = false;
    private boolean gameOver = false;
    private boolean paused = false;

    // 蛇颜色属性
    private final Color[] skinColors = {Color.RED, Color.YELLOW, Color.BLUE, Color.GREEN, Color.ORANGE, Color.CYAN, Color.MAGENTA}; // 皮肤颜色数组
    private int currentColorIndex = 3; // 当前颜色索引(默认绿色)
    private Color snakeColor = skinColors[currentColorIndex]; // 默认蛇颜色（从颜色数组获取以保持一致性）

    // 游戏组件
    private GamePanel gamePanel = new GamePanel(); // 初始化面板避免空指针
    private Timer timer;

    // 蛇的属性
    private int snakeLength;
    private List<Point> snakeSegments; // 使用Point对象管理蛇身位置
    private Direction currentDirection; // 当前移动方向
    private Direction nextDirection; // 下一个方向(用于输入队列)

    // 苹果（食物）属性
    private int appleX, appleY;
    private int score;

    public SnakeGame() {
        setTitle("贪吃蛇游戏");
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setResizable(false);

        initGame();
        pack(); // 调整窗口大小以适应内容面板
        setLocationRelativeTo(null);
        setVisible(true);
    }

    private void initGame() {
        // 检查并切换输入法
        java.awt.im.InputContext inputContext = java.awt.im.InputContext.getInstance();
        if (inputContext.getLocale() != null) {
            String currentLocale = inputContext.getLocale().toString();
            // 检查是否为中文输入法
            if (currentLocale.contains("zh")) {
                // 切换到英文输入法
                inputContext.selectInputMethod(java.util.Locale.ENGLISH);
            }
        }

        running = true;
        gameOver = false;
        snakeLength = 3;
        currentDirection = Direction.RIGHT;
        nextDirection = Direction.RIGHT;

        // 初始化蛇的位置
        snakeSegments = new ArrayList<>();
        initializeSnake();

        generateApple();  // 生成苹果
        score = 0;

        // 创建计时器（每100ms更新一次游戏）
        currentTimerDelay = BASE_TIMER_DELAY; // 初始化当前延迟
        timer = new Timer(currentTimerDelay, e -> {
            if (running && !gameOver && !paused) {
                moveSnake();
                checkCollision();
                checkApple();
                gamePanel.repaint();
            }
        });

        // 初始化游戏面板
        if (gamePanel != null) {
            remove(gamePanel);
        }
        gamePanel = new GamePanel();
        gamePanel.setFocusable(true);
        gamePanel.addKeyListener(this); // 将键盘监听器添加到游戏面板
        add(gamePanel);
        // 延迟请求焦点以确保面板可见后获得焦点
        SwingUtilities.invokeLater(() -> gamePanel.requestFocusInWindow());

        timer.start();  // 启动游戏循环
    }

    // 优化：生成不与蛇身重叠的苹果（添加最大尝试次数防止死循环）
    private void generateApple() {
        Random rand = new Random();
        boolean appleOnSnake;
        int maxAttempts = 10000;  // 最大尝试次数
        int attempts = 0;
        // 计算苹果生成范围（确保在可见区域内）
        int maxX = (GAME_WIDTH - 30) / GRID_SIZE;
        int maxY = (GAME_HEIGHT - 50) / GRID_SIZE;

        // 创建蛇位置集合用于快速碰撞检测
        Set<Point> snakePositions = new HashSet<>(snakeSegments);

        do {
            appleOnSnake = false;
            // 生成苹果坐标（10x10网格）
            appleX = 10 + GRID_SIZE * rand.nextInt(maxX);  // X范围：10-(GAME_WIDTH-20)
            appleY = 30 + GRID_SIZE * rand.nextInt(maxY);  // Y范围：30-(GAME_HEIGHT-20)

            // 检查是否与蛇身重叠
            Point applePoint = new Point(appleX, appleY);
            if (snakePositions.contains(applePoint)) {
                appleOnSnake = true;
            }
            attempts++;
        } while (appleOnSnake && attempts < maxAttempts);  // 最多尝试10000次

        if (appleOnSnake) {
            // 多次尝试后仍无法生成苹果，放宽条件强制生成
            // 线性搜索第一个可用位置，确保苹果可见
            boolean found = false;
            outerLoop:
            for (int x = 10; x <= 590; x += 10) {
                for (int y = 20; y <= 390; y += 10) {
                    boolean positionAvailable = true;
                    for (int i = 0; i < snakeSegments.size(); i++) {
                        Point segment = snakeSegments.get(i);
                        if (segment.x == x && segment.y == y) {
                            positionAvailable = false;
                            break;
                        }
                    }
                    if (positionAvailable) {
                        appleX = x;
                        appleY = y;
                        found = true;
                        break outerLoop;
                    }
                }
            }

            if (!found) {
                // 作为最后的备选方案，使用随机位置
                appleX = 10 + 10 * rand.nextInt(59);
                appleY = 20 + 10 * rand.nextInt(38);
            }
            SwingUtilities.invokeLater(() -> JOptionPane.showMessageDialog(this, "警告：苹果生成区域不足，游戏可能出现异常！", "警告", JOptionPane.WARNING_MESSAGE));}
    }

    // 移动蛇（从蛇尾到蛇头逐节移动）
    private void moveSnake() {
        // 从蛇尾开始，将前一节的位置复制到当前节
        for (int i = snakeSegments.size() - 1; i > 0; i--) {
            Point prev = snakeSegments.get(i - 1);
            snakeSegments.set(i, new Point(prev.x, prev.y));
        }

        // 获取当前头部位置
        Point head = snakeSegments.get(0);
        int headX = head.x;
        int headY = head.y;

        // 应用下一个方向（如果已设置）
        if (nextDirection != null) {
            currentDirection = nextDirection;
            nextDirection = null;
        }

        // 根据当前方向计算新头部位置
        switch (currentDirection) {
            case UP: headY -= GRID_SIZE; break;
            case RIGHT: headX += GRID_SIZE; break;
            case DOWN: headY += GRID_SIZE; break;
            case LEFT: headX -= GRID_SIZE; break;
        }

        // 更新头部位置
        snakeSegments.set(0, new Point(headX, headY));


    }

    // 检查碰撞（边界/自身）
    private void checkCollision() {
        // 边界碰撞检测（使用常量定义边界，提高可读性）
        final int LEFT_BOUND = 0;
        final int RIGHT_BOUND = GAME_WIDTH - GRID_SIZE;
        final int TOP_BOUND = 0;
        final int BOTTOM_BOUND = GAME_HEIGHT - GRID_SIZE;

        Point head = snakeSegments.get(0);
        int headX = head.x;
        int headY = head.y;

        if (headX < LEFT_BOUND || headX > RIGHT_BOUND || headY < TOP_BOUND || headY > BOTTOM_BOUND) {
            gameOver();
            return;
        }

        // 自身碰撞检测
        for (int i = 1; i < snakeSegments.size(); i++) {
            if (head.equals(snakeSegments.get(i))) {
                gameOver();
                return;
            }
        }
    }

    // 检查是否吃到苹果（吃后长度+1）
    private void checkApple() {
        // 检查是否吃到苹果（直接坐标比较，提高效率）
        Point head = snakeSegments.get(0);
        int headX = head.x;
        int headY = head.y;

        if (headX == appleX && headY == appleY) {
            // 在蛇尾添加新节
            Point tail = snakeSegments.get(snakeSegments.size() - 1);
            snakeSegments.add(new Point(tail));
            snakeLength++;
            score += 10;
            // 检查是否达到最大长度
            if (snakeLength >= MAX_SNAKE_LENGTH) {
                snakeLength = MAX_SNAKE_LENGTH;
                SwingUtilities.invokeLater(() -> JOptionPane.showMessageDialog(this, "恭喜! 你已达到最大长度!"));
            }
            generateApple();
            // 随着分数增加提高游戏速度
            if (score % 50 == 0 && currentTimerDelay > 50) {
                currentTimerDelay -= 5; // 降低延迟，提高速度
                timer.setDelay(currentTimerDelay);
            }
        }
    }

    // 循环切换蛇颜色
    private void cycleSnakeColor() {
        currentColorIndex = (currentColorIndex + 1) % skinColors.length;
        snakeColor = skinColors[currentColorIndex];
    }

    // 获取当前颜色名称
    private String getCurrentColorName() {
        return switch(currentColorIndex) {
            case 0 -> "红色";
            case 1 -> "黄色";
            case 2 -> "蓝色";
            case 3 -> "绿色";
            case 4 -> "橙色";
            case 5 -> "青色";
            case 6 -> "紫色";
            default -> "默认";
        };
    }

    // 游戏结束
    private void gameOver() {
        running = false;
        gameOver = true;
        timer.stop();

        // 创建自定义对话框以更好地控制焦点管理
        JOptionPane optionPane = new JOptionPane(String.format("游戏结束!\n得分: %d\n按R键重新开始", score), JOptionPane.INFORMATION_MESSAGE);
        JDialog dialog = optionPane.createDialog(this, "游戏结束");
        dialog.setModal(true); // 设置为模态对话框

        // 添加对话框关闭监听器，确保在对话框关闭后请求焦点
        dialog.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosed(WindowEvent e) {
                SwingUtilities.invokeLater(() -> {
                    gamePanel.requestFocusInWindow();
                    gamePanel.setFocusable(true);
                });
            }
        });

        dialog.setVisible(true);
    }

    // 重新开始游戏（关键修改：移除旧面板并请求焦点）
    public void resetGame() {
        // 重置游戏状态
        snakeSegments.clear();
        snakeLength = 3;
        score = 0;
        gameOver = false;
        currentDirection = Direction.RIGHT;
        nextDirection = Direction.RIGHT;
        currentTimerDelay = BASE_TIMER_DELAY;
        timer.setDelay(currentTimerDelay);

        initializeSnake();
        generateApple();
        repaint();
        running = true;
        timer.start();
        // 确保在EDT上设置焦点
        SwingUtilities.invokeLater(() -> {
            gamePanel.requestFocusInWindow();
            gamePanel.setFocusable(true);
        });
    }

    // 初始化蛇的位置
    private void initializeSnake() {
        int startX = GAME_WIDTH / 2;
        int startY = GAME_HEIGHT / 2;
        snakeSegments = new ArrayList<>();
        for (int i = 0; i < snakeLength; i++) {
            snakeSegments.add(new Point(startX - i * GRID_SIZE, startY));
        }
    }

    // 游戏面板（绘制所有元素）
    private class GamePanel extends JPanel {
        private BufferedImage backgroundImage;
        // 确保面板可以获得焦点
        public GamePanel() {
            setFocusable(true);
            setRequestFocusEnabled(true);
            // 加载背景图
            try {
                backgroundImage = ImageIO.read(getClass().getResourceAsStream("/resources/background.jpg"));
            } catch (IOException e) {
                backgroundImage = null;
                System.out.println("警告：无法加载背景图片！");
            }
        }

        @Override
        public Dimension getPreferredSize() {
            return new Dimension(GAME_WIDTH, GAME_HEIGHT);
        }

        @Override
        protected void paintComponent(Graphics g) {
            super.paintComponent(g);
            drawBackground(g);
            drawApple(g);
            drawSnake(g);
            drawHUD(g);
            drawGameStates(g);
        }

        private void drawBackground(Graphics g) {
            if (backgroundImage != null) {
                g.drawImage(backgroundImage, 0, 0, getWidth(), getHeight(), this);
            } else {
                g.setColor(Color.BLACK);
                g.fillRect(0, 0, getWidth(), getHeight());
            }
        }

        private void drawApple(Graphics g) {
            // 绘制像素风格苹果
            int[][] pixels = {
                    {0, 0, 1, 1, 1, 1, 1, 1, 0, 0},
                    {0, 1, 1, 1, 1, 1, 1, 1, 1, 0},
                    {1, 1, 1, 1, 1, 1, 1, 1, 1, 1},
                    {1, 1, 1, 1, 2, 2, 1, 1, 1, 1},
                    {1, 1, 1, 2, 2, 2, 2, 1, 1, 1},
                    {1, 1, 1, 1, 2, 2, 1, 1, 1, 1},
                    {1, 1, 1, 1, 1, 1, 1, 1, 1, 1},
                    {1, 1, 1, 1, 1, 1, 1, 1, 1, 1},
                    {0, 1, 1, 1, 1, 1, 1, 1, 1, 0},
                    {0, 0, 1, 1, 1, 1, 1, 1, 0, 0}
            };

            // 绘制苹果主体像素
            for (int y = 0; y < 10; y++) {
                for (int x = 0; x < 10; x++) {
                    int colorType = pixels[y][x];
                    if (colorType == 1) {
                        g.setColor(Color.RED);
                        g.fillRect(appleX + x, appleY + y, 1, 1);
                    } else if (colorType == 2) {
                        g.setColor(Color.YELLOW);
                        g.fillRect(appleX + x, appleY + y, 1, 1);
                    }
                }
            }

            // 绘制绿色的茎
            g.setColor(new Color(34, 139, 34)); // 森林绿
            g.fillRect(appleX + 4, appleY - 2, 1, 2); // 主茎
            g.fillRect(appleX + 3, appleY - 4, 1, 2); // 左分支
            g.fillRect(appleX + 5, appleY - 3, 1, 1); // 右分支
        }

        private void drawSnake(Graphics g) {
            g.setColor(snakeColor);
            for (int i = 0; i < snakeLength; i++) {
                Point segment = snakeSegments.get(i);
                g.fillRect(segment.x, segment.y, GRID_SIZE, GRID_SIZE);
            }
        }

        private void drawHUD(Graphics g) {
            g.setFont(GAME_FONT_BOLD_16);
            g.setColor(Color.WHITE);
            g.drawString(String.format("分数: %d", score), 10, 20);
            g.drawString(String.format("颜色: %s (按C键切换)", getCurrentColorName()), 120, 20);
        }

        private void drawGameStates(Graphics g) {
            if (paused) {
                g.setColor(Color.WHITE);
                g.setFont(GAME_FONT_BOLD_24);
                String pauseMessage = "游戏暂停，按空格键继续";
                int messageWidth = g.getFontMetrics().stringWidth(pauseMessage);
                g.drawString(pauseMessage, (getWidth() - messageWidth) / 2, getHeight() / 2);
            }

            if (gameOver) {
                g.setColor(Color.WHITE);
                g.setFont(GAME_FONT_BOLD_24);
                String line1 = "游戏结束!";
                String line2 = String.format("得分: %d", score);
                String line3 = "按R键重新开始";
                int line1Width = g.getFontMetrics().stringWidth(line1);
                int line2Width = g.getFontMetrics().stringWidth(line2);
                int line3Width = g.getFontMetrics().stringWidth(line3);
                int lineHeight = g.getFontMetrics().getHeight();
                g.drawString(line1, (getWidth() - line1Width) / 2, getHeight() / 2 - lineHeight);
                g.drawString(line2, (getWidth() - line2Width) / 2, getHeight() / 2);
                g.drawString(line3, (getWidth() - line3Width) / 2, getHeight() / 2 + lineHeight);
            }
        }
    }

    // 键盘事件监听（优化焦点和按键处理）
    @Override
    public void keyPressed(KeyEvent e) {
        if (!gamePanel.hasFocus()) {
            gamePanel.requestFocusInWindow();
            return;
        }

        if (gameOver || !running) {
            // 游戏未开始或结束时，仅响应R键
            if (e.getKeyCode() == KeyEvent.VK_R) {
                resetGame();
            }
            return;
        }

        if (paused) {
            // 暂停状态下只响应空格键
            if (e.getKeyCode() == KeyEvent.VK_SPACE) {
                paused = false;
                timer.start();
                gamePanel.repaint();
            }
            return;
        }

        int key = e.getKeyCode();
        // 根据按键改变方向（不能反向移动）
        switch (key) {
            case KeyEvent.VK_UP:
                if (currentDirection != Direction.DOWN) {
                    nextDirection = Direction.UP;
                }
                break;
            case KeyEvent.VK_RIGHT:
                if (currentDirection != Direction.LEFT) {
                    nextDirection = Direction.RIGHT;
                }
                break;
            case KeyEvent.VK_DOWN:
                if (currentDirection != Direction.UP) {
                    nextDirection = Direction.DOWN;
                }
                break;
            case KeyEvent.VK_LEFT:
                if (currentDirection != Direction.RIGHT) {
                    nextDirection = Direction.LEFT;
                }
                break;
            case KeyEvent.VK_SPACE:
                paused = true;
                timer.stop();
                gamePanel.repaint();
                break;
            case KeyEvent.VK_C:
                cycleSnakeColor();
                gamePanel.repaint();
                break;
        }
    }

    @Override
    public void keyReleased(KeyEvent ignored) {}
    @Override
    public void keyTyped(KeyEvent ignored) {}

    @SuppressWarnings("unused")
    public static void main(String[] args) {
        // 抑制未使用参数警告
        SwingUtilities.invokeLater(SnakeGame::new);
    }
}
